# Copyright (c) 2013 TrilioData, Inc.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
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

"""
Backup job scheduler manages backup jobs


**Related Flags**

:backupjobs_topic:  What :mod:`rpc` topic to listen to (default:
                        `raksha-backupjobs`).
:backupjobs_manager:  The module name of a class derived from
                          :class:`manager.Manager` (default:
                          :class:`raksha.backupjob.manager.Manager`).

"""

from sqlalchemy import *
from datetime import datetime, timedelta
import time
import uuid

from oslo.config import cfg

from raksha import context
from raksha import exception
from raksha import flags
from raksha import manager
from raksha.virt import driver
from raksha.openstack.common import excutils
from raksha.openstack.common import importutils
from raksha.openstack.common import log as logging
from raksha.apscheduler.scheduler import Scheduler

from raksha.vault import swift

LOG = logging.getLogger(__name__)

backupjobs_manager_opts = [
    cfg.StrOpt('vault_service',
               default='raksha.vault.swift',
               help='Vault to use for backup jobs.'),
]

scheduler_config = {'standalone': 'True'}

FLAGS = flags.FLAGS
FLAGS.register_opts(backupjobs_manager_opts)

def backupjob_callback(backupjob_id):
    """
    Callback
    """
    #TODO(gbasava): Implementation


class BackupJobManager(manager.SchedulerDependentManager):
    """Manages backup jobs """

    RPC_API_VERSION = '1.0'

    def __init__(self, service_name=None, *args, **kwargs):

        self.service = importutils.import_module(FLAGS.vault_service)
        self.az = FLAGS.storage_availability_zone
        self.scheduler = Scheduler(scheduler_config)
        self.scheduler.start()

        super(BackupJobManager, self).__init__(service_name='backupjobscheduler',
                                            *args, **kwargs)
        self.driver = driver.load_compute_driver(None, None)

    def init_host(self):
        """
        Do any initialization that needs to be run if this is a standalone service.
        """

        ctxt = context.get_admin_context()

        LOG.info(_("Cleaning up incomplete backup operations"))

    def backupjob_create(self, context, backupjob_id):
        """
        Create a scheduled backup job in the backup job scheduler
        """
        try:
            backupjob = self.db.backupjob_get(context, backupjob_id)
            #TODO(gbasava): Change it to list of VMs when we support multiple VMs
            vm = self.db.backupjob_vms_get(context, backupjob_id)

            LOG.info(_('create_backupjob started, %s:' %backupjob_id))
            self.db.backupjob_update(context, backupjob_id, {'host': self.host,
                                     'service': FLAGS.vault_service})

            schjob = self.scheduler.add_interval_job(context, backupjob_callback, hours=24,
                                     name=backupjob['display_name'], args=[backupjob_id], 
                                     backupjob_id=backupjob_id)
            LOG.info(_('scheduled backup job: %s'), schjob.id)
        except Exception as err:
            with excutils.save_and_reraise_exception():
                self.db.backupjob_update(context, backupjob_id,
                                      {'status': 'error',
                                       'fail_reason': unicode(err)})

        self.db.backupjob_update(context, backupjob_id, {'status': 'available',
                                                         'availability_zone': self.az,
                                                         'schedule_job_id':schjob.id})
        LOG.info(_('create_backupjob finished. backup: %s'), backupjob_id)

    def backupjob_execute(self, context, backupjobrun_id):
        """
        Execute the backup job. Invoked by the scheduler
        """
        LOG.info(_('execute_backupjob started, backupjobrun_id %s:' %backupjobrun_id))
        backupjobrun = self.db.backupjobrun_get(context, backupjobrun_id)

        """
        Make sure the backup job is prepared before scheduling an incremental backup
        """
        backupjob = self.db.backupjob_get(context, backupjobrun.backupjob_id)
        self.db.backupjobrun_update(context, backupjobrun.id, {'status': 'executing'})
        #TODO(gbasava): Pick the specified vault service for the backup job
        vault_service = swift.SwiftBackupService(context)
        #take a backup of each VM
        for vm in self.db.backupjob_vms_get(context, backupjobrun.backupjob_id): 
            #create an entry for the VM
            options = {'vm_id': vm.vm_id,
                       'backupjobrun_id': backupjobrun_id,
                       'backuptype':'incremental',
                       'status': 'creating'}
            backupjobrun_vm = self.db.backupjobrun_vm_create(context, options) 
            self.driver.backup_execute(backupjob, backupjobrun, backupjobrun_vm, vault_service, self.db, context)
            #TODO(gbasava): Check for the success (and update)
            backupjobrun_vm.update({'status': 'available',})
            #TODO(gbasava): handle the case where this can be updated by multiple backup job runs coming from 
            #different backup jobs.
            self.db.vm_recent_backupjobrun_update(context, vm.vm_id, {'backupjobrun_id': backupjobrun.id})
            
        #TODO(gbasava): Check for the success (and update)                
        self.db.backupjobrun_update(context, backupjobrun.id, {'status': 'available'})             
            
    def backupjob_prepare(self, context, backupjobrun_id):
        """
        Prepare the backup job by doing a full backup 
        """
        LOG.info(_('prepare_backupjob started, backupjobrun_id %s:' %backupjobrun_id))
        backupjobrun = self.db.backupjobrun_get(context, backupjobrun_id)

        # Backup job preparation can only be executed once
        if (backupjobrun.backuptype == "full" and backupjobrun.status == "completed"):
            return;

        backupjob = self.db.backupjob_get(context, backupjobrun.backupjob_id)
        self.db.backupjobrun_update(context, backupjobrun.id, {'status': 'executing'})
        #TODO(gbasava): Pick the specified vault service for the backup job
        vault_service = swift.SwiftBackupService(context)
        
        #take a backup of each VM
        for vm in self.db.backupjob_vms_get(context, backupjobrun.backupjob_id): 
            #create an entry for the VM
            options = {'vm_id': vm.vm_id,
                       'backupjobrun_id': backupjobrun_id,
                       'backuptype':'full',
                       'status': 'creating',}
            backupjobrun_vm = self.db.backupjobrun_vm_create(context, options) 
            self.driver.backup_prepare(backupjob, backupjobrun, backupjobrun_vm, vault_service, self.db, context)
            #TODO(gbasava): Check for the success (and update)
            backupjobrun_vm.update({'status': 'available',})
            #TODO(gbasava): handle the case where this can be updated by multiple backup job runs coming from 
            #different backup jobs.
            self.db.vm_recent_backupjobrun_update(context, vm.vm_id, {'backupjobrun_id': backupjobrun.id})
        
        #TODO(gbasava): Check for the success (and update)                
        self.db.backupjobrun_update(context, backupjobrun.id, {'status': 'available'})    

    def backupjob_delete(self, context, backupjob_id):
        """
        Delete an existing backupjob
        """
        backup = self.db.backup_get(context, backupjob_id)
        LOG.info(_('delete_backup started, backup: %s'), backupjob_id)
        #TODO(gbasava): Implement

    def backupjobrun_restore(self, context, backupjobrun_id):
        """
        Restore VMs and all its LUNs from a backup job run
        """
        LOG.info(_('restore_backupjobrun started, restoring backupjobrun id: %(backupjobrun_id)s') % locals())
        backupjobrun = self.db.backupjobrun_get(context, backupjobrun_id)
        backupjob = self.db.backupjob_get(context, backupjobrun.backupjob_id)
        #self.db.backupjobrun_update(context, backupjobrun.id, {'status': 'restoring'})
        #TODO(gbasava): Pick the specified vault service from the backupjobrun
        vault_service = swift.SwiftBackupService(context)
        
        #restore each VM
        for vm in self.db.backupjobrun_vm_get(context, backupjobrun.id): 
            self.driver.restore_instance(backupjob, backupjobrun, vm, vault_service, self.db, context)


    def backupjobrun_delete(self, context, backupjobrun_id):
        """
        Delete an existing backupjobrun
        """
        backup = self.db.backup_get(context, backupjob_id, backupjob_instance_id)
        #TODO(gbasava):Implement
 