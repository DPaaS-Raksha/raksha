"""
This module is the main part of the library. It houses the Scheduler class
and related exceptions.
"""

from threading import Thread, Event, Lock
from datetime import datetime, timedelta
from logging import getLogger

import os
import sys

from oslo.config import cfg
from raksha import context as ctx

from raksha import flags
from raksha.openstack.common import importutils

from raksha.apscheduler.util import *
from raksha.apscheduler.triggers import SimpleTrigger, IntervalTrigger, CronTrigger
from raksha.apscheduler.job import Job, MaxInstancesReachedError
from raksha.apscheduler.events import *
from raksha.apscheduler.threadpool import ThreadPool

logger = getLogger(__name__)

db_driver_opt = cfg.StrOpt('db_driver',
                           default='raksha.db',
                           help='driver to use for database access')

FLAGS = flags.FLAGS
FLAGS.register_opt(db_driver_opt)


class SchedulerAlreadyRunningError(Exception):
    """
    Raised when attempting to start or configure the scheduler when it's
    already running.
    """

    def __str__(self):
        return 'Scheduler is already running'


class Scheduler(object):
    """
    This class is responsible for scheduling jobs and triggering
    their execution.
    """

    _stopped = False
    _thread = None

    def __init__(self, gconfig={}, **options):
        self._wakeup = Event()
        self._listeners = []
        self._listeners_lock = Lock()
        self._pending_jobs = []
        self.db = importutils.import_module(FLAGS.db_driver)
        self.configure(gconfig, **options)

    def configure(self, gconfig={}, **options):
        """
        Reconfigures the scheduler with the given options. Can only be done
        when the scheduler isn't running.
        """
        if self.running:
            raise SchedulerAlreadyRunningError

        # Set general options
        config = combine_opts(gconfig, 'apscheduler.', options)
        self.misfire_grace_time = int(config.pop('misfire_grace_time', 1))
        self.coalesce = asbool(config.pop('coalesce', True))
        self.daemonic = asbool(config.pop('daemonic', True))
        self.standalone = asbool(config.pop('standalone', False))

        # Configure the thread pool
        if 'threadpool' in config:
            self._threadpool = maybe_ref(config['threadpool'])
        else:
            threadpool_opts = combine_opts(config, 'threadpool.')
            self._threadpool = ThreadPool(**threadpool_opts)

    def start(self):
        """
        Starts the scheduler in a new thread.

        In threaded mode (the default), this method will return immediately
        after starting the scheduler thread.

        In standalone mode, this method will block until there are no more
        scheduled jobs.
        """
        if self.running:
            raise SchedulerAlreadyRunningError

        # Schedule all pending jobs
        for job, jobstore in self._pending_jobs:
            self._real_add_job(job, jobstore, False)

        self._stopped = False
        if self.standalone:
            self._main_loop()
        else:
            self._thread = Thread(target=self._main_loop, name='APScheduler')
            self._thread.setDaemon(self.daemonic)
            self._thread.start()

    def shutdown(self, wait=True, shutdown_threadpool=True):
        """
        Shuts down the scheduler and terminates the thread.
        Does not interrupt any currently running jobs.

        :param wait: ``True`` to wait until all currently executing jobs have
                     finished (if ``shutdown_threadpool`` is also ``True``)
        :param shutdown_threadpool: ``True`` to shut down the thread pool
        :param close_jobstores: ``True`` to close all job stores after shutdown
        """
        if not self.running:
            return

        self._stopped = True
        self._wakeup.set()

        # Shut down the thread pool
        if shutdown_threadpool:
            self._threadpool.shutdown(wait)

        # Wait until the scheduler thread terminates
        if self._thread:
            self._thread.join()


    @property
    def running(self):
        return not self._stopped and self._thread and self._thread.isAlive()


    def add_listener(self, callback, mask=EVENT_ALL):
        """
        Adds a listener for scheduler events. When a matching event occurs,
        ``callback`` is executed with the event object as its sole argument.
        If the ``mask`` parameter is not provided, the callback will receive
        events of all types.

        :param callback: any callable that takes one argument
        :param mask: bitmask that indicates which events should be listened to
        """
        self._listeners_lock.acquire()
        try:
            self._listeners.append((callback, mask))
        finally:
            self._listeners_lock.release()

    def remove_listener(self, callback):
        """
        Removes a previously added event listener.
        """
        self._listeners_lock.acquire()
        try:
            for i, (cb, _) in enumerate(self._listeners):
                if callback == cb:
                    del self._listeners[i]
        finally:
            self._listeners_lock.release()

    def _notify_listeners(self, event):
        self._listeners_lock.acquire()
        try:
            listeners = tuple(self._listeners)
        finally:
            self._listeners_lock.release()

        for cb, mask in listeners:
            if event.code & mask:
                try:
                    cb(event)
                except:
                    logger.exception('Error notifying listener')

    def _real_add_job(self, context, job, wakeup):
        job.compute_next_run_time(datetime.now())
        if not job.next_run_time:
            raise ValueError('Not adding job since it would never be run')

        self.db.scheduledjob_create(context, job)

        # Notify listeners that a new job has been added
        event = JobStoreEvent(EVENT_JOBSTORE_JOB_ADDED, None, job)
        self._notify_listeners(event)

        logger.info('Added job "%s"', job)

        # Notify the scheduler about the new job
        if wakeup:
            self._wakeup.set()

    def add_job(self, context, trigger, func, args, kwargs, **options):
        """
        Adds the given job to the job list and notifies the scheduler thread.
        Any extra keyword arguments are passed along to the constructor of the
        :class:`~apscheduler.job.Job` class (see :ref:`job_options`).

        :param trigger: trigger that determines when ``func`` is called
        :param func: callable to run at the given time
        :param args: list of positional arguments to call func with
        :param kwargs: dict of keyword arguments to call func with
        :rtype: :class:`~apscheduler.job.Job`
        """
        job = Job(trigger, func, args or [], kwargs or {},
                  options.pop('misfire_grace_time', self.misfire_grace_time),
                  options.pop('coalesce', self.coalesce), **options)
        if not self.running:
            self._pending_jobs.append((job))
            logger.info('Adding job tentatively -- it will be properly '
                        'scheduled when the scheduler starts')
        else:
            self._real_add_job(context, job, True)
        return job

    def _remove_job(self, job, alias):
        self.db.scheduledjob_delete(job.id)

        # Notify listeners that a job has been removed
        event = JobStoreEvent(EVENT_JOBSTORE_JOB_REMOVED, alias, job)
        self._notify_listeners(event)

        logger.info('Removed job "%s"', job)

    def add_date_job(self, context, func, date, args=None, kwargs=None, **options):
        """
        Schedules a job to be completed on a specific date and time.
        Any extra keyword arguments are passed along to the constructor of the
        :class:`~apscheduler.job.Job` class (see :ref:`job_options`).

        :param func: callable to run at the given time
        :param date: the date/time to run the job at
        :param name: name of the job
        :param misfire_grace_time: seconds after the designated run time that
            the job is still allowed to be run
        :type date: :class:`datetime.date`
        :rtype: :class:`~apscheduler.job.Job`
        """
        trigger = SimpleTrigger(date)
        return self.add_job(trigger, func, args, kwargs, **options)

    def add_interval_job(self, context, func, weeks=0, days=0, hours=0, minutes=0,
                         seconds=0, start_date=None, args=None, kwargs=None,
                         **options):
        """
        Schedules a job to be completed on specified intervals.
        Any extra keyword arguments are passed along to the constructor of the
        :class:`~apscheduler.job.Job` class (see :ref:`job_options`).

        :param func: callable to run
        :param weeks: number of weeks to wait
        :param days: number of days to wait
        :param hours: number of hours to wait
        :param minutes: number of minutes to wait
        :param seconds: number of seconds to wait
        :param start_date: when to first execute the job and start the
            counter (default is after the given interval)
        :param args: list of positional arguments to call func with
        :param kwargs: dict of keyword arguments to call func with
        :param name: name of the job
        :param misfire_grace_time: seconds after the designated run time that
            the job is still allowed to be run
        :rtype: :class:`~apscheduler.job.Job`
        """
        interval = timedelta(weeks=weeks, days=days, hours=hours,
                             minutes=minutes, seconds=seconds)
        trigger = IntervalTrigger(interval, start_date)
        return self.add_job(context, trigger, func, args, kwargs, **options)

    def add_cron_job(self, func, year=None, month=None, day=None, week=None,
                     day_of_week=None, hour=None, minute=None, second=None,
                     start_date=None, args=None, kwargs=None, **options):
        """
        Schedules a job to be completed on times that match the given
        expressions.
        Any extra keyword arguments are passed along to the constructor of the
        :class:`~apscheduler.job.Job` class (see :ref:`job_options`).

        :param func: callable to run
        :param year: year to run on
        :param month: month to run on
        :param day: day of month to run on
        :param week: week of the year to run on
        :param day_of_week: weekday to run on (0 = Monday)
        :param hour: hour to run on
        :param second: second to run on
        :param args: list of positional arguments to call func with
        :param kwargs: dict of keyword arguments to call func with
        :param name: name of the job
        :param misfire_grace_time: seconds after the designated run time that
            the job is still allowed to be run
        :return: the scheduled job
        :rtype: :class:`~apscheduler.job.Job`
        """
        trigger = CronTrigger(year=year, month=month, day=day, week=week,
                              day_of_week=day_of_week, hour=hour,
                              minute=minute, second=second,
                              start_date=start_date)
        return self.add_job(trigger, func, args, kwargs, **options)

    def cron_schedule(self, **options):
        """
        Decorator version of :meth:`add_cron_job`.
        This decorator does not wrap its host function.
        Unscheduling decorated functions is possible by passing the ``job``
        attribute of the scheduled function to :meth:`unschedule_job`.
        Any extra keyword arguments are passed along to the constructor of the
        :class:`~apscheduler.job.Job` class (see :ref:`job_options`).
        """
        def inner(func):
            func.job = self.add_cron_job(func, **options)
            return func
        return inner

    def interval_schedule(self, **options):
        """
        Decorator version of :meth:`add_interval_job`.
        This decorator does not wrap its host function.
        Unscheduling decorated functions is possible by passing the ``job``
        attribute of the scheduled function to :meth:`unschedule_job`.
        Any extra keyword arguments are passed along to the constructor of the
        :class:`~apscheduler.job.Job` class (see :ref:`job_options`).
        """
        def inner(func):
            func.job = self.add_interval_job(func, **options)
            return func
        return inner

    def get_job(self, context, job_id):
        for  job in self.db.scheduledjob_get(context):
             if job.id == job_id:
                    return job


    def unschedule_job(self, job):
        """
        Removes a job, preventing it from being run any more.
        """
        self._jobstores_lock.acquire()
        try:
            for alias, jobstore in iteritems(self._jobstores):
                if job in list(jobstore.jobs):
                    self._remove_job(job, alias, jobstore)
                    return
        finally:
            self._jobstores_lock.release()

        raise KeyError('Job "%s" is not scheduled in any job store' % job)

    def unschedule_func(self, func):
        """
        Removes all jobs that would execute the given function.
        """
        found = False
        self._jobstores_lock.acquire()
        try:
            for alias, jobstore in iteritems(self._jobstores):
                for job in list(jobstore.jobs):
                    if job.func == func:
                        self._remove_job(job, alias, jobstore)
                        found = True
        finally:
            self._jobstores_lock.release()

        if not found:
            raise KeyError('The given function is not scheduled in this '
                           'scheduler')

    def print_jobs(self, out=None):
        """
        Prints out a textual listing of all jobs currently scheduled on this
        scheduler.

        :param out: a file-like object to print to (defaults to **sys.stdout**
                    if nothing is given)
        """
        out = out or sys.stdout
        job_strs = []
        self._jobstores_lock.acquire()
        try:
            for alias, jobstore in iteritems(self._jobstores):
                job_strs.append('Jobstore %s:' % alias)
                if jobstore.jobs:
                    for job in jobstore.jobs:
                        job_strs.append('    %s' % job)
                else:
                    job_strs.append('    No scheduled jobs')
        finally:
            self._jobstores_lock.release()

        out.write(os.linesep.join(job_strs) + os.linesep)

    def _run_job(self, job, run_times):
        """
        Acts as a harness that runs the actual job code in a thread.
        """
        for run_time in run_times:
            # See if the job missed its run time window, and handle possible
            # misfires accordingly
            difference = datetime.now() - run_time
            grace_time = timedelta(seconds=job.misfire_grace_time)
            if difference > grace_time:
                # Notify listeners about a missed run
                event = JobEvent(EVENT_JOB_MISSED, job, run_time)
                self._notify_listeners(event)
                logger.warning('Run time of job "%s" was missed by %s',
                               job, difference)
            else:
                try:
                    job.add_instance()
                except MaxInstancesReachedError:
                    event = JobEvent(EVENT_JOB_MISSED, job, run_time)
                    self._notify_listeners(event)
                    logger.warning('Execution of job "%s" skipped: '
                                   'maximum number of running instances '
                                   'reached (%d)', job, job.max_instances)
                    break

                logger.info('Running job "%s" (scheduled at %s)', job,
                            run_time)

                try:
                    retval = job.func(*job.args, **job.kwargs)
                except:
                    # Notify listeners about the exception
                    exc, tb = sys.exc_info()[1:]
                    event = JobEvent(EVENT_JOB_ERROR, job, run_time,
                                     exception=exc, traceback=tb)
                    self._notify_listeners(event)

                    logger.exception('Job "%s" raised an exception', job)
                else:
                    # Notify listeners about successful execution
                    event = JobEvent(EVENT_JOB_EXECUTED, job, run_time,
                                     retval=retval)
                    self._notify_listeners(event)

                    logger.info('Job "%s" executed successfully', job)

                job.remove_instance()

                # If coalescing is enabled, don't attempt any further runs
                if job.coalesce:
                    break

    def _process_jobs(self, now):
        """
        Iterates through jobs in every jobstore, starts pending jobs
        and figures out the next wakeup time.
        """
        next_wakeup_time = None
        for job in self.db.scheduledjob_get(ctx.get_admin_context()):
            run_times = job.get_run_times(now)
            if run_times:
                self._threadpool.submit(self._run_job, job, run_times)

            # Increase the job's run count
            if job.coalesce:
                 job.runs += 1
            else:
                 job.runs += len(run_times)

            # Update the job, but don't keep finished jobs around
            if job.compute_next_run_time(now + timedelta(microseconds=1)):
                 self.db.scheduledjob_update(ctx.get_admin_context(), job)
            else:
                 self._remove_job(job, alias)

            if not next_wakeup_time:
                next_wakeup_time = job.next_run_time
            elif job.next_run_time:
                next_wakeup_time = min(next_wakeup_time,
                                               job.next_run_time)
        return next_wakeup_time

    def _main_loop(self):
        """Executes jobs on schedule."""

        logger.info('Scheduler started')
        self._notify_listeners(SchedulerEvent(EVENT_SCHEDULER_START))

        self._wakeup.clear()
        while not self._stopped:
            logger.debug('Looking for jobs to run')
            now = datetime.now()
            next_wakeup_time = self._process_jobs(now)

            # Sleep until the next job is scheduled to be run,
            # a new job is added or the scheduler is stopped
            if next_wakeup_time is not None:
                wait_seconds = time_difference(next_wakeup_time, now)
                logger.debug('Next wakeup is due at %s (in %f seconds)',
                             next_wakeup_time, wait_seconds)
                self._wakeup.wait(wait_seconds)
                self._wakeup.clear()
            elif self.standalone:
                logger.debug('No jobs left; shutting down scheduler')
                self.shutdown()
                break
            else:
                logger.debug('No jobs; waiting until a job is added')
                self._wakeup.wait()
                self._wakeup.clear()

        logger.info('Scheduler has been shut down')
        self._notify_listeners(SchedulerEvent(EVENT_SCHEDULER_SHUTDOWN))
