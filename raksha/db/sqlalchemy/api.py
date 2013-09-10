# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2013 TrilioData, Inc.
# Copyright (c) 2011 X.commerce, a business unit of eBay Inc.
# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Implementation of SQLAlchemy backend."""

import datetime
import uuid
import warnings

import sqlalchemy
import sqlalchemy.orm as sa_orm
import sqlalchemy.sql as sa_sql

from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_
from sqlalchemy.orm import joinedload
from sqlalchemy.sql.expression import literal_column
from sqlalchemy.sql import func

from raksha.common import sqlalchemyutils
from raksha import db
from raksha.db.sqlalchemy import models
from raksha.db.sqlalchemy.session import get_session
from raksha import exception
from raksha import flags
from raksha.openstack.common import log as logging
from raksha.openstack.common import timeutils
from raksha.openstack.common import uuidutils
from raksha.apscheduler import job


FLAGS = flags.FLAGS

LOG = logging.getLogger(__name__)


def is_admin_context(context):
    """Indicates if the request context is an administrator."""
    if not context:
        warnings.warn(_('Use of empty request context is deprecated'),
                      DeprecationWarning)
        raise Exception('die')
    return context.is_admin


def is_user_context(context):
    """Indicates if the request context is a normal user."""
    if not context:
        return False
    if context.is_admin:
        return False
    if not context.user_id or not context.project_id:
        return False
    return True


def authorize_project_context(context, project_id):
    """Ensures a request has permission to access the given project."""
    if is_user_context(context):
        if not context.project_id:
            raise exception.NotAuthorized()
        elif context.project_id != project_id:
            raise exception.NotAuthorized()


def authorize_user_context(context, user_id):
    """Ensures a request has permission to access the given user."""
    if is_user_context(context):
        if not context.user_id:
            raise exception.NotAuthorized()
        elif context.user_id != user_id:
            raise exception.NotAuthorized()


def authorize_quota_class_context(context, class_name):
    """Ensures a request has permission to access the given quota class."""
    if is_user_context(context):
        if not context.quota_class:
            raise exception.NotAuthorized()
        elif context.quota_class != class_name:
            raise exception.NotAuthorized()


def require_admin_context(f):
    """Decorator to require admin request context.

    The first argument to the wrapped function must be the context.

    """

    def wrapper(*args, **kwargs):
        if not is_admin_context(args[0]):
            raise exception.AdminRequired()
        return f(*args, **kwargs)
    return wrapper


def require_context(f):
    """Decorator to require *any* user or admin context.

    This does no authorization for user or project access matching, see
    :py:func:`authorize_project_context` and
    :py:func:`authorize_user_context`.

    The first argument to the wrapped function must be the context.

    """

    def wrapper(*args, **kwargs):
        if not is_admin_context(args[0]) and not is_user_context(args[0]):
            raise exception.NotAuthorized()
        return f(*args, **kwargs)
    return wrapper

def model_query(context, *args, **kwargs):
    """Query helper that accounts for context's `read_deleted` field.

    :param context: context to query under
    :param session: if present, the session to use
    :param read_deleted: if present, overrides context's read_deleted field.
    :param project_only: if present and context is user-type, then restrict
            query to match the context's project_id.
    """
    session = kwargs.get('session') or get_session()
    read_deleted = kwargs.get('read_deleted') or context.read_deleted
    project_only = kwargs.get('project_only')

    query = session.query(*args)

    if read_deleted == 'no':
        query = query.filter_by(deleted=False)
    elif read_deleted == 'yes':
        pass  # omit the filter to include deleted and active
    elif read_deleted == 'only':
        query = query.filter_by(deleted=True)
    else:
        raise Exception(
            _("Unrecognized read_deleted value '%s'") % read_deleted)

    if project_only and is_user_context(context):
        query = query.filter_by(project_id=context.project_id)

    return query


def exact_filter(query, model, filters, legal_keys):
    """Applies exact match filtering to a query.

    Returns the updated query.  Modifies filters argument to remove
    filters consumed.

    :param query: query to apply filters to
    :param model: model object the query applies to, for IN-style
                  filtering
    :param filters: dictionary of filters; values that are lists,
                    tuples, sets, or frozensets cause an 'IN' test to
                    be performed, while exact matching ('==' operator)
                    is used for other values
    :param legal_keys: list of keys to apply exact filtering to
    """

    filter_dict = {}

    # Walk through all the keys
    for key in legal_keys:
        # Skip ones we're not filtering on
        if key not in filters:
            continue

        # OK, filtering on this key; what value do we search for?
        value = filters.pop(key)

        if isinstance(value, (list, tuple, set, frozenset)):
            # Looking for values in a list; apply to query directly
            column_attr = getattr(model, key)
            query = query.filter(column_attr.in_(value))
        else:
            # OK, simple exact match; save for later
            filter_dict[key] = value

    # Apply simple exact matches
    if filter_dict:
        query = query.filter_by(**filter_dict)

    return query


###################


@require_admin_context
def service_destroy(context, service_id):
    session = get_session()
    with session.begin():
        service_ref = service_get(context, service_id, session=session)
        service_ref.delete(session=session)


@require_admin_context
def service_get(context, service_id, session=None):
    result = model_query(
        context,
        models.Service,
        session=session).\
        filter_by(id=service_id).\
        first()
    if not result:
        raise exception.ServiceNotFound(service_id=service_id)

    return result


@require_admin_context
def service_get_all(context, disabled=None):
    query = model_query(context, models.Service)

    if disabled is not None:
        query = query.filter_by(disabled=disabled)

    return query.all()


@require_admin_context
def service_get_all_by_topic(context, topic):
    return model_query(
        context, models.Service, read_deleted="no").\
        filter_by(disabled=False).\
        filter_by(topic=topic).\
        all()


@require_admin_context
def service_get_by_host_and_topic(context, host, topic):
    result = model_query(
        context, models.Service, read_deleted="no").\
        filter_by(disabled=False).\
        filter_by(host=host).\
        filter_by(topic=topic).\
        first()
    if not result:
        raise exception.ServiceNotFound(service_id=None)
    return result


@require_admin_context
def service_get_all_by_host(context, host):
    return model_query(
        context, models.Service, read_deleted="no").\
        filter_by(host=host).\
        all()


@require_admin_context
def _service_get_all_topic_subquery(context, session, topic, subq, label):
    sort_value = getattr(subq.c, label)
    return model_query(context, models.Service,
                       func.coalesce(sort_value, 0),
                       session=session, read_deleted="no").\
        filter_by(topic=topic).\
        filter_by(disabled=False).\
        outerjoin((subq, models.Service.host == subq.c.host)).\
        order_by(sort_value).\
        all()


@require_admin_context
def service_get_all_volume_sorted(context):
    session = get_session()
    with session.begin():
        topic = FLAGS.volume_topic
        label = 'volume_gigabytes'
        subq = model_query(context, models.Volume.host,
                           func.sum(models.Volume.size).label(label),
                           session=session, read_deleted="no").\
            group_by(models.Volume.host).\
            subquery()
        return _service_get_all_topic_subquery(context,
                                               session,
                                               topic,
                                               subq,
                                               label)


@require_admin_context
def service_get_by_args(context, host, binary):
    result = model_query(context, models.Service).\
        filter_by(host=host).\
        filter_by(binary=binary).\
        first()

    if not result:
        raise exception.HostBinaryNotFound(host=host, binary=binary)

    return result


@require_admin_context
def service_create(context, values):
    service_ref = models.Service()
    service_ref.update(values)
    if not FLAGS.enable_new_services:
        service_ref.disabled = True
    service_ref.save()
    return service_ref


@require_admin_context
def service_update(context, service_id, values):
    session = get_session()
    with session.begin():
        service_ref = service_get(context, service_id, session=session)
        service_ref.update(values)
        service_ref.save(session=session)


###################


def _metadata_refs(metadata_dict, meta_class):
    metadata_refs = []
    if metadata_dict:
        for k, v in metadata_dict.iteritems():
            metadata_ref = meta_class()
            metadata_ref['key'] = k
            metadata_ref['value'] = v
            metadata_refs.append(metadata_ref)
    return metadata_refs


def _dict_with_extra_specs(inst_type_query):
    """Takes an instance, volume, or instance type query returned
    by sqlalchemy and returns it as a dictionary, converting the
    extra_specs entry from a list of dicts:

    'extra_specs' : [{'key': 'k1', 'value': 'v1', ...}, ...]

    to a single dict:

    'extra_specs' : {'k1': 'v1'}

    """
    inst_type_dict = dict(inst_type_query)
    extra_specs = dict([(x['key'], x['value'])
                        for x in inst_type_query['extra_specs']])
    inst_type_dict['extra_specs'] = extra_specs
    return inst_type_dict


###################


@require_context
def quota_get(context, project_id, resource, session=None):
    result = model_query(context, models.Quota, session=session,
                         read_deleted="no").\
        filter_by(project_id=project_id).\
        filter_by(resource=resource).\
        first()

    if not result:
        raise exception.ProjectQuotaNotFound(project_id=project_id)

    return result


@require_context
def quota_get_all_by_project(context, project_id):
    authorize_project_context(context, project_id)

    rows = model_query(context, models.Quota, read_deleted="no").\
        filter_by(project_id=project_id).\
        all()

    result = {'project_id': project_id}
    for row in rows:
        result[row.resource] = row.hard_limit

    return result


@require_admin_context
def quota_create(context, project_id, resource, limit):
    quota_ref = models.Quota()
    quota_ref.project_id = project_id
    quota_ref.resource = resource
    quota_ref.hard_limit = limit
    quota_ref.save()
    return quota_ref


@require_admin_context
def quota_update(context, project_id, resource, limit):
    session = get_session()
    with session.begin():
        quota_ref = quota_get(context, project_id, resource, session=session)
        quota_ref.hard_limit = limit
        quota_ref.save(session=session)


@require_admin_context
def quota_destroy(context, project_id, resource):
    session = get_session()
    with session.begin():
        quota_ref = quota_get(context, project_id, resource, session=session)
        quota_ref.delete(session=session)


###################


@require_context
def quota_class_get(context, class_name, resource, session=None):
    result = model_query(context, models.QuotaClass, session=session,
                         read_deleted="no").\
        filter_by(class_name=class_name).\
        filter_by(resource=resource).\
        first()

    if not result:
        raise exception.QuotaClassNotFound(class_name=class_name)

    return result


@require_context
def quota_class_get_all_by_name(context, class_name):
    authorize_quota_class_context(context, class_name)

    rows = model_query(context, models.QuotaClass, read_deleted="no").\
        filter_by(class_name=class_name).\
        all()

    result = {'class_name': class_name}
    for row in rows:
        result[row.resource] = row.hard_limit

    return result


@require_admin_context
def quota_class_create(context, class_name, resource, limit):
    quota_class_ref = models.QuotaClass()
    quota_class_ref.class_name = class_name
    quota_class_ref.resource = resource
    quota_class_ref.hard_limit = limit
    quota_class_ref.save()
    return quota_class_ref


@require_admin_context
def quota_class_update(context, class_name, resource, limit):
    session = get_session()
    with session.begin():
        quota_class_ref = quota_class_get(context, class_name, resource,
                                          session=session)
        quota_class_ref.hard_limit = limit
        quota_class_ref.save(session=session)


@require_admin_context
def quota_class_destroy(context, class_name, resource):
    session = get_session()
    with session.begin():
        quota_class_ref = quota_class_get(context, class_name, resource,
                                          session=session)
        quota_class_ref.delete(session=session)


@require_admin_context
def quota_class_destroy_all_by_name(context, class_name):
    session = get_session()
    with session.begin():
        quota_classes = model_query(context, models.QuotaClass,
                                    session=session, read_deleted="no").\
            filter_by(class_name=class_name).\
            all()

        for quota_class_ref in quota_classes:
            quota_class_ref.delete(session=session)


###################


@require_context
def quota_usage_get(context, project_id, resource, session=None):
    result = model_query(context, models.QuotaUsage, session=session,
                         read_deleted="no").\
        filter_by(project_id=project_id).\
        filter_by(resource=resource).\
        first()

    if not result:
        raise exception.QuotaUsageNotFound(project_id=project_id)

    return result


@require_context
def quota_usage_get_all_by_project(context, project_id):
    authorize_project_context(context, project_id)

    rows = model_query(context, models.QuotaUsage, read_deleted="no").\
        filter_by(project_id=project_id).\
        all()

    result = {'project_id': project_id}
    for row in rows:
        result[row.resource] = dict(in_use=row.in_use, reserved=row.reserved)

    return result


@require_admin_context
def quota_usage_create(context, project_id, resource, in_use, reserved,
                       until_refresh, session=None):
    quota_usage_ref = models.QuotaUsage()
    quota_usage_ref.project_id = project_id
    quota_usage_ref.resource = resource
    quota_usage_ref.in_use = in_use
    quota_usage_ref.reserved = reserved
    quota_usage_ref.until_refresh = until_refresh
    quota_usage_ref.save(session=session)

    return quota_usage_ref


###################


@require_context
def reservation_get(context, uuid, session=None):
    result = model_query(context, models.Reservation, session=session,
                         read_deleted="no").\
        filter_by(uuid=uuid).first()

    if not result:
        raise exception.ReservationNotFound(uuid=uuid)

    return result


@require_context
def reservation_get_all_by_project(context, project_id):
    authorize_project_context(context, project_id)

    rows = model_query(context, models.Reservation, read_deleted="no").\
        filter_by(project_id=project_id).all()

    result = {'project_id': project_id}
    for row in rows:
        result.setdefault(row.resource, {})
        result[row.resource][row.uuid] = row.delta

    return result


@require_admin_context
def reservation_create(context, uuid, usage, project_id, resource, delta,
                       expire, session=None):
    reservation_ref = models.Reservation()
    reservation_ref.uuid = uuid
    reservation_ref.usage_id = usage['id']
    reservation_ref.project_id = project_id
    reservation_ref.resource = resource
    reservation_ref.delta = delta
    reservation_ref.expire = expire
    reservation_ref.save(session=session)
    return reservation_ref


@require_admin_context
def reservation_destroy(context, uuid):
    session = get_session()
    with session.begin():
        reservation_ref = reservation_get(context, uuid, session=session)
        reservation_ref.delete(session=session)


###################


# NOTE(johannes): The quota code uses SQL locking to ensure races don't
# cause under or over counting of resources. To avoid deadlocks, this
# code always acquires the lock on quota_usages before acquiring the lock
# on reservations.

def _get_quota_usages(context, session, project_id):
    # Broken out for testability
    rows = model_query(context, models.QuotaUsage,
                       read_deleted="no",
                       session=session).\
        filter_by(project_id=project_id).\
        with_lockmode('update').\
        all()
    return dict((row.resource, row) for row in rows)


@require_context
def quota_reserve(context, resources, quotas, deltas, expire,
                  until_refresh, max_age, project_id=None):
    elevated = context.elevated()
    session = get_session()
    with session.begin():
        if project_id is None:
            project_id = context.project_id

        # Get the current usages
        usages = _get_quota_usages(context, session, project_id)

        # Handle usage refresh
        work = set(deltas.keys())
        while work:
            resource = work.pop()

            # Do we need to refresh the usage?
            refresh = False
            if resource not in usages:
                usages[resource] = quota_usage_create(elevated,
                                                      project_id,
                                                      resource,
                                                      0, 0,
                                                      until_refresh or None,
                                                      session=session)
                refresh = True
            elif usages[resource].in_use < 0:
                # Negative in_use count indicates a desync, so try to
                # heal from that...
                refresh = True
            elif usages[resource].until_refresh is not None:
                usages[resource].until_refresh -= 1
                if usages[resource].until_refresh <= 0:
                    refresh = True
            elif max_age and (usages[resource].updated_at -
                              timeutils.utcnow()).seconds >= max_age:
                refresh = True

            # OK, refresh the usage
            if refresh:
                # Grab the sync routine
                sync = resources[resource].sync

                updates = sync(elevated, project_id, session)
                for res, in_use in updates.items():
                    # Make sure we have a destination for the usage!
                    if res not in usages:
                        usages[res] = quota_usage_create(elevated,
                                                         project_id,
                                                         res,
                                                         0, 0,
                                                         until_refresh or None,
                                                         session=session)

                    # Update the usage
                    usages[res].in_use = in_use
                    usages[res].until_refresh = until_refresh or None

                    # Because more than one resource may be refreshed
                    # by the call to the sync routine, and we don't
                    # want to double-sync, we make sure all refreshed
                    # resources are dropped from the work set.
                    work.discard(res)

                    # NOTE(Vek): We make the assumption that the sync
                    #            routine actually refreshes the
                    #            resources that it is the sync routine
                    #            for.  We don't check, because this is
                    #            a best-effort mechanism.

        # Check for deltas that would go negative
        unders = [resource for resource, delta in deltas.items()
                  if delta < 0 and
                  delta + usages[resource].in_use < 0]

        # Now, let's check the quotas
        # NOTE(Vek): We're only concerned about positive increments.
        #            If a project has gone over quota, we want them to
        #            be able to reduce their usage without any
        #            problems.
        overs = [resource for resource, delta in deltas.items()
                 if quotas[resource] >= 0 and delta >= 0 and
                 quotas[resource] < delta + usages[resource].total]

        # NOTE(Vek): The quota check needs to be in the transaction,
        #            but the transaction doesn't fail just because
        #            we're over quota, so the OverQuota raise is
        #            outside the transaction.  If we did the raise
        #            here, our usage updates would be discarded, but
        #            they're not invalidated by being over-quota.

        # Create the reservations
        if not overs:
            reservations = []
            for resource, delta in deltas.items():
                reservation = reservation_create(elevated,
                                                 str(uuid.uuid4()),
                                                 usages[resource],
                                                 project_id,
                                                 resource, delta, expire,
                                                 session=session)
                reservations.append(reservation.uuid)

                # Also update the reserved quantity
                # NOTE(Vek): Again, we are only concerned here about
                #            positive increments.  Here, though, we're
                #            worried about the following scenario:
                #
                #            1) User initiates resize down.
                #            2) User allocates a new instance.
                #            3) Resize down fails or is reverted.
                #            4) User is now over quota.
                #
                #            To prevent this, we only update the
                #            reserved value if the delta is positive.
                if delta > 0:
                    usages[resource].reserved += delta

        # Apply updates to the usages table
        for usage_ref in usages.values():
            usage_ref.save(session=session)

    if unders:
        LOG.warning(_("Change will make usage less than 0 for the following "
                      "resources: %(unders)s") % locals())
    if overs:
        usages = dict((k, dict(in_use=v['in_use'], reserved=v['reserved']))
                      for k, v in usages.items())
        raise exception.OverQuota(overs=sorted(overs), quotas=quotas,
                                  usages=usages)

    return reservations


def _quota_reservations(session, context, reservations):
    """Return the relevant reservations."""

    # Get the listed reservations
    return model_query(context, models.Reservation,
                       read_deleted="no",
                       session=session).\
        filter(models.Reservation.uuid.in_(reservations)).\
        with_lockmode('update').\
        all()


@require_context
def reservation_commit(context, reservations, project_id=None):
    session = get_session()
    with session.begin():
        usages = _get_quota_usages(context, session, project_id)

        for reservation in _quota_reservations(session, context, reservations):
            usage = usages[reservation.resource]
            if reservation.delta >= 0:
                usage.reserved -= reservation.delta
            usage.in_use += reservation.delta

            reservation.delete(session=session)

        for usage in usages.values():
            usage.save(session=session)


@require_context
def reservation_rollback(context, reservations, project_id=None):
    session = get_session()
    with session.begin():
        usages = _get_quota_usages(context, session, project_id)

        for reservation in _quota_reservations(session, context, reservations):
            usage = usages[reservation.resource]
            if reservation.delta >= 0:
                usage.reserved -= reservation.delta

            reservation.delete(session=session)

        for usage in usages.values():
            usage.save(session=session)


@require_admin_context
def quota_destroy_all_by_project(context, project_id):
    session = get_session()
    with session.begin():
        quotas = model_query(context, models.Quota, session=session,
                             read_deleted="no").\
            filter_by(project_id=project_id).\
            all()

        for quota_ref in quotas:
            quota_ref.delete(session=session)

        quota_usages = model_query(context, models.QuotaUsage,
                                   session=session, read_deleted="no").\
            filter_by(project_id=project_id).\
            all()

        for quota_usage_ref in quota_usages:
            quota_usage_ref.delete(session=session)

        reservations = model_query(context, models.Reservation,
                                   session=session, read_deleted="no").\
            filter_by(project_id=project_id).\
            all()

        for reservation_ref in reservations:
            reservation_ref.delete(session=session)


@require_admin_context
def reservation_expire(context):
    session = get_session()
    with session.begin():
        current_time = timeutils.utcnow()
        results = model_query(context, models.Reservation, session=session,
                              read_deleted="no").\
            filter(models.Reservation.expire < current_time).\
            all()

        if results:
            for reservation in results:
                if reservation.delta >= 0:
                    reservation.usage.reserved -= reservation.delta
                    reservation.usage.save(session=session)

                reservation.delete(session=session)


###############################


@require_context
def backupjob_get(context, backupjob_id, session=None):
    result = model_query(context, models.BackupJob,
                             session=session, project_only=True).\
        filter_by(id=backupjob_id).\
        first()

    if not result:
        raise exception.BackupJobNotFound(backupjob_id=backupjob_id)

    return result

@require_context
def backupjob_show(context, backupjob_id, session=None):
    result = model_query(context, models.BackupJob,
                             session=session, project_only=True).\
        filter_by(id=backupjob_id).\
        first()
    if not result:
        raise exception.BackupJobNotFound(backupjob_id=backupjob_id)

    return result

@require_admin_context
def backupjob_get_all(context):
    return model_query(context, models.BackupJob).all()


@require_admin_context
def backupjob_get_all_by_host(context, host):
    return model_query(context, models.BackupJob).filter_by(host=host).all()


@require_context
def backupjob_get_all_by_project(context, project_id):
    authorize_project_context(context, project_id)

    return model_query(context, models.BackupJob).\
        filter_by(project_id=project_id).all()


@require_context
def backupjob_create(context, values):
    backupjob = models.BackupJob()
    if not values.get('id'):
        values['id'] = str(uuid.uuid4())
    backupjob.update(values)
    backupjob.save()
    return backupjob


@require_context
def backupjob_update(context, backupjob_id, values):
    session = get_session()
    with session.begin():
        backupjob = model_query(context, models.BackupJob,
                             session=session, read_deleted="yes").\
            filter_by(id=backupjob_id).first()

        if not backupjob:
            raise exception.BackupJobNotFound(
                _("No backup job with id %(backupjob_id)s") % locals())

        backupjob.update(values)
        backupjob.save(session=session)
    return backupjob


@require_context
def backupjob_destroy(context, backupjob_id):
    session = get_session()
    with session.begin():
        session.query(models.BackupJob).\
            filter_by(id=backupjob_id).\
            update({'status': 'deleted',
                    'deleted': True,
                    'deleted_at': timeutils.utcnow(),
                    'updated_at': literal_column('updated_at')})

@require_context
def backupjob_vms_create(context, values):
    backupjob_vm = models.BackupJobVMs()
    if not values.get('id'):
        values['id'] = str(uuid.uuid4())
    backupjob_vm.update(values)
    backupjob_vm.save()
    return backupjob_vm

@require_context
def backupjob_vms_get(context, backupjob_id, session=None):
    result = model_query(context, models.BackupJobVMs,
                             session=session).\
        filter_by(backupjob_id=backupjob_id).\
        all()

    if not result:
        raise exception.VMsofBackupJobNotFound(backupjob_id=backupjob_id)

    return result

@require_context
def backupjob_vms_destroy(context, vm_id, backupjob_id):
    session = get_session()
    with session.begin():
        session.query(models.BackupJobVMs).\
            filter_by(vm_id=vm_id).\
            filter_by(backupjob_id=backupjob_id).\
            update({'status': 'deleted',
                    'deleted': True,
                    'deleted_at': timeutils.utcnow(),
                    'updated_at': literal_column('updated_at')})
                    
@require_context
def scheduledjob_create(context, scheduledjob):
    values = scheduledjob.__getstate__()
    schjob = models.ScheduledJobs()
    if not values.get('id'):
        values['id'] = str(uuid.uuid4())
    schjob.update(values)
    schjob.save()
    return schjob

@require_context
def scheduledjob_delete(context, id):
    session = get_session()
    with session.begin():
        session.query(models.ScheduledJobs).\
            filter_by(id=id).\
            update({'status': 'deleted',
                    'deleted': True,
                    'deleted_at': timeutils.utcnow(),
                    'updated_at': literal_column('updated_at')})

@require_context
def scheduledjob_get(context):
    scheduledjob = []
    rows =  model_query(context, models.ScheduledJobs).all()
    for row in rows:
        try:
            j = job.Job.__new__(job.Job)
            job_dict = dict(row.__dict__)
            j.__setstate__(job_dict)
            scheduledjob.append(j)
        except Exception:
            logger.exception('Unable to schedule jobs')
    return scheduledjob

@require_context
def scheduledjob_update(context, scheduledjob):
    session = get_session()
    values = scheduledjob.__getstate__()
    del values['_sa_instance_state']
    with session.begin():
        dbjob = model_query(context, models.ScheduledJobs,
                             session=session, read_deleted="yes").\
            filter_by(id=scheduledjob.id).first()

        if not dbjob:
            raise exception.BackupJobNotFound(
                _("No backup job with id %s"), scheduledjob.id)

        dbjob.update(values)
        dbjob.save(session=session)
        return dbjob

@require_context
def backupjobrun_get(context, backupjobrun_id, session=None):
    result = model_query(context, models.BackupJobRuns,
                             session=session).\
        filter_by(id=backupjobrun_id).\
        first()

    if not result:
        raise exception.BackupJobRunNotFound(backupjobrun_id=backupjobrun_id)

    return result

@require_admin_context
def backupjobrun_get_all(context):
    return model_query(context, models.BackupJobRuns).all()

@require_context
def backupjobrun_get_all_by_project(context, project_id):
    authorize_project_context(context, project_id)

    return model_query(context, models.BackupJobRuns).\
        filter_by(project_id=project_id).all()

@require_context
def backupjobrun_show(context, backupjobrun_id, session=None):
    result = model_query(context, models.BackupJobRuns,
                             session=session).\
        filter_by(id=backupjobrun_id).\
        first()

    if not result:
        raise exception.BackupJobRunNotFound(backupjobrun_id=backupjobrun_id)

    return result

@require_context
def backupjobrun_create(context, values):
    backupjobrun = models.BackupJobRuns()
    if not values.get('id'):
        values['id'] = str(uuid.uuid4())
    backupjobrun.update(values)
    backupjobrun.save()
    return backupjobrun

@require_context
def backupjobrun_update(context, backupjobrun_id, values):
    session = get_session()
    with session.begin():
        backupjobrun = model_query(context, models.BackupJobRuns,
                             session=session, read_deleted="yes").\
            filter_by(id=backupjobrun_id).first()

        if not backupjobrun:
            raise exception.BackupJobRunNotFound(
                _("No backup job run with id %(backupjobrun_id)s") % locals())

        backupjobrun.update(values)
        backupjobrun.save(session=session)
    return backupjobrun

@require_context
def backupjobrun_destroy(context, backupjobrun_id):
    session = get_session()
    with session.begin():
        session.query(models.BackupJobRuns).\
            filter_by(id=backupjobrun_id).\
            update({'status': 'deleted',
                    'deleted': True,
                    'deleted_at': timeutils.utcnow(),
                    'updated_at': literal_column('updated_at')})

@require_context
def backupjobrun_vm_create(context, values):
    backupjobrun_vm = models.BackupJobRunVMs()
    if not values.get('id'):
        values['id'] = str(uuid.uuid4())
    backupjobrun_vm.update(values)
    backupjobrun_vm.save()
    return backupjobrun_vm

@require_context
def backupjobrun_vm_get(context, backupjobrun_id, session=None):
    result = model_query(context, models.BackupJobRunVMs,
                             session=session).\
        filter_by(backupjobrun_id=backupjobrun_id).\
        all()

    if not result:
        raise exception.VMsOfBackupJobRunNotFound(backupjobrun_id=backupjobrun_id)

    return result

@require_context
def backupjobrun_vm_destroy(context, vm_id, backupjobrun_id):
    session = get_session()
    with session.begin():
        session.query(models.BackupJobRunVMs).\
            filter_by(vm_id=vm_id).\
            filter_by(backupjobrun_id=backupjobrun_id).\
            update({'status': 'deleted',
                    'deleted': True,
                    'deleted_at': timeutils.utcnow(),
                    'updated_at': literal_column('updated_at')})

@require_context
def vm_recent_backupjobrun_create(context, values):
    vm_recent_backupjobrun = models.VMRecentBackupJobRun()
    vm_recent_backupjobrun.update(values)
    vm_recent_backupjobrun.save()
    return vm_recent_backupjobrun

@require_context
def vm_recent_backupjobrun_get(context, vm_id, session=None):
    result = model_query(context, models.VMRecentBackupJobRun,
                             session=session).\
        filter_by(vm_id=vm_id).\
        first()

    if not result:
        raise exception.VMRecentBackupJobRunNotFound(vm_id=vm_id)

    return result

@require_context
def vm_recent_backupjobrun_update(context, vm_id, values):
    session = get_session()
    with session.begin():
        vm_recent_backupjobrun = model_query(context, models.VMRecentBackupJobRun,
                             session=session, read_deleted="yes").\
            filter_by(vm_id = vm_id).first()

        if not vm_recent_backupjobrun:
            #raise exception.VMRecentBackupJobRunNotFound(
            #    _("Recent backupjobrun for VM %(vm_id)s is not found") % locals())
            values['vm_id'] = vm_id
            vm_recent_backupjobrun = models.VMRecentBackupJobRun()
            
        vm_recent_backupjobrun.update(values)
        vm_recent_backupjobrun.save(session=session)
        
    return vm_recent_backupjobrun

@require_context
def vm_recent_backupjobrun_destroy(context, vm_id):
    session = get_session()
    with session.begin():
        session.query(models.VMRecentBackupJobRun).\
            filter_by(vm_id=vm_id).\
            update({'status': 'deleted',
                    'deleted': True,
                    'deleted_at': timeutils.utcnow(),
                    'updated_at': literal_column('updated_at')})

require_context
def backupjobrun_vm_resource_create(context, values):
    backupjobrun_vm_resource = models.BackupJobRunVMResources()
    if not values.get('id'):
        values['id'] = str(uuid.uuid4())
    backupjobrun_vm_resource.update(values)
    backupjobrun_vm_resource.save()
    return backupjobrun_vm_resource

@require_context
def backupjobrun_vm_resources_get(context, vm_id, backupjobrun_id, session=None):
    result = model_query(context, models.BackupJobRunVMResources,
                             session=session).\
        filter_by(vm_id=vm_id).\
        filter_by(backupjobrun_id=backupjobrun_id).\
        all()

    if not result:
        raise exception.BackupJobRunVMResourcesNotFound(vm_id = vm_id, backupjobrun_id = backupjobrun_id)

    return result

@require_context
def backupjobrun_vm_resource_get(context, vm_id, backupjobrun_id, resource_name, session=None):
    result = model_query(context, models.BackupJobRunVMResources,
                             session=session).\
        filter_by(vm_id=vm_id).\
        filter_by(backupjobrun_id=backupjobrun_id).\
        filter_by(resource_name=resource_name).\
        first()

    if not result:
        raise exception.BackupJobRunVMResourcesWithNameNotFound(vm_id = vm_id, 
                                                        backupjobrun_id = backupjobrun_id,
                                                        resource_name = resource_name)

    return result

def backupjobrun_vm_resource_get2(context, id, session=None):
    result = model_query(context, models.BackupJobRunVMResources,
                             session=session).\
        filter_by(id=id).\
        first()

    if not result:
        raise exception.BackupJobRunVMResourcesWithIdNotFound(id = id)

    return result

@require_context
def backupjobrun_vm_resource_destroy(context, id, vm_id, backupjobrun_id):
    session = get_session()
    with session.begin():
        session.query(models.BackupJobRunVMResources).\
            filter_by(id=id).\
            filter_by(vm_id=vm_id).\
            filter_by(backupjobrun_id=backupjobrun_id).\
            update({'status': 'deleted',
                    'deleted': True,
                    'deleted_at': timeutils.utcnow(),
                    'updated_at': literal_column('updated_at')})

def _set_metadata_for_vm_resource_backup(context, vm_resource_backup_ref, metadata,
                              purge_metadata=False, session=None):
    """
    Create or update a set of vm_resource_backup_metadata for a given image

    :param context: Request context
    :param image_ref: An vm_resource_backup object
    :param metadata: A dict of metadata to set
    :param session: A SQLAlchemy session to use (if present)
    """
    orig_metadata = {}
    for metadata_ref in vm_resource_backup_ref.metadata:
        orig_metadata[metadata_ref.key] = metadata_ref

    for key, value in metadata.iteritems():
        metadata_values = {'vm_resource_backup_id': vm_resource_backup_ref.id,
                           'key': key,
                           'value': value}
        if key in orig_metadata:
            metadata_ref = orig_metadata[key]
            _vm_resource_backup_metadata_update(context, metadata_ref, metadata_values,
                                   session=session)
        else:
            vm_resource_backup_metadata_create(context, metadata_values, session=session)

    if purge_metadata:
        for key in orig_metadata.keys():
            if key not in metadata:
                metadata_ref = orig_metadata[key]
                vm_resource_backup_metadata_delete(context, metadata_ref, session=session)


def vm_resource_backup_metadata_create(context, values, session=None):
    """Create an VMResourceBackupMetadata object"""
    metadata_ref = models.VMResourceBackupMetadata()
    if not values.get('id'):
        values['id'] = str(uuid.uuid4())    
    return _vm_resource_backup_metadata_update(context, metadata_ref, values, session=session)


def _vm_resource_backup_metadata_update(context, metadata_ref, values, session=None):
    """
    Used internally by vm_resource_backup_metadata_create and vm_resource_backup_metadata_update
    """
    session = get_session()
    values["deleted"] = False
    metadata_ref.update(values)
    metadata_ref.save(session=session)
    return metadata_ref


def vm_resource_backup_metadata_delete(context, metadata_ref, session=None):
    """
    Used internally by vm_resource_backup_metadata_create and vm_resource_backup_metadata_update
    """
    session = get_session()
    metadata_ref.delete(session=session)
    return metadata_ref

def _vm_resource_backup_update(context, values, backupjobrun_vm_resource_id, purge_metadata=False):
    
    metadata = values.pop('metadata', {})
    
    if backupjobrun_vm_resource_id:
        vm_resource_backup_ref = vm_resource_backups_get(context, backupjobrun_vm_resource_id, None)
    else:
        vm_resource_backup_ref = models.VMResourceBackups()
    if not values.get('id'):
        values['id'] = str(uuid.uuid4())
    vm_resource_backup_ref.update(values)
    vm_resource_backup_ref.save()
    
    _set_metadata_for_vm_resource_backup(context, vm_resource_backup_ref, metadata, purge_metadata)  
      
    return vm_resource_backup_ref


@require_context
def vm_resource_backup_create(context, values):
    
    return _vm_resource_backup_update(context, values, None, False)

def vm_resource_backup_update(context, backupjobrun_vm_resource_id, values, purge_metadata=False):
   
    return _vm_resource_backup_update(context, values, backupjobrun_vm_resource_id, purge_metadata)

@require_context
def vm_resource_backups_get(context, backupjobrun_vm_resource_id, session=None):
    session = get_session()
    try:
        query = session.query(models.VMResourceBackups)\
                       .options(sa_orm.joinedload(models.VMResourceBackups.metadata))\
                       .filter_by(backupjobrun_vm_resource_id=backupjobrun_vm_resource_id)

        #TODO(gbasava): filter out deleted backups if context disallows it
        vm_resource_backups = query.all()

    except sa_orm.exc.NoResultFound:
        raise exception.VMResourceBackupsNotFound(backupjobrun_vm_resource_id = backupjobrun_vm_resource_id)
    
    return vm_resource_backups

@require_context
def vm_resource_backup_get_top(context, backupjobrun_vm_resource_id, session=None):
    session = get_session()
    try:
        query = session.query(models.VMResourceBackups)\
                       .options(sa_orm.joinedload(models.VMResourceBackups.metadata))\
                       .filter_by(backupjobrun_vm_resource_id = backupjobrun_vm_resource_id)\
                       .filter_by(top= True)

        #TODO(gbasava): filter out resource backups if context disallows it
        vm_resource_backup = query.one()

    except sa_orm.exc.NoResultFound:
        raise exception.VMResourceBackupsNotFound(backupjobrun_vm_resource_id = backupjobrun_vm_resource_id)
    
    return vm_resource_backup

@require_context
def vm_resource_backup_get(context, vm_resource_backup_id, session=None):
    session = get_session()
    try:
        query = session.query(models.VMResourceBackups)\
                       .options(sa_orm.joinedload(models.VMResourceBackups.metadata))\
                       .filter_by(id= vm_resource_backup_id)

        #TODO(gbasava): filter out deleted resource backups if context disallows it
        vm_resource_backup = query.one()

    except sa_orm.exc.NoResultFound:
        raise exception.VMResourceBackupsNotFound(vm_resource_backup_id = vm_resource_backup_id)
    
    return vm_resource_backup


@require_context
def vm_resource_backups_destroy(context, backupjobrun_vm_resource_id):
    session = get_session()
    with session.begin():
        session.query(models.VMResourceBackups).\
            filter_by(backupjobrun_vm_resource_id=backupjobrun_vm_resource_id).\
            update({'status': 'deleted',
                    'deleted': True,
                    'deleted_at': timeutils.utcnow(),
                    'updated_at': literal_column('updated_at')})
    

@require_context
def vault_service_create(context, values):
    vault_service = models.VaultServices()
    if not values.get('id'):
        values['id'] = str(uuid.uuid4())
    vault_service.update(values)
    vault_service.save()
    return vault_service

@require_context
def vault_service_get(context, id, session=None):
    result = model_query(context, models.VaultServices,
                             session=session).\
        filter_by(id=id).\
        all()

    if not result:
        raise exception.BackupServiceNotFound(id=id)

    return result

@require_context
def vault_service_destroy(context, id):
    session = get_session()
    with session.begin():
        session.query(models.VaultServices).\
            filter_by(id=id).\
            update({'status': 'deleted',
                    'deleted': True,
                    'deleted_at': timeutils.utcnow(),
                    'updated_at': literal_column('updated_at')})
