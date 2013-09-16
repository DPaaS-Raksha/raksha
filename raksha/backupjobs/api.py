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
Handles all requests relating to the  backup jobs service.
"""
import socket

from eventlet import greenthread

from raksha.backupjobs import rpcapi as backupjobs_rpcapi
from raksha.db import base
from raksha import exception
from raksha import flags
from raksha.openstack.common import log as logging


FLAGS = flags.FLAGS

LOG = logging.getLogger(__name__)


class API(base.Base):
    """API for interacting with the DPaaS manager."""

    def __init__(self, db_driver=None):
        self.backupjobs_rpcapi = backupjobs_rpcapi.BackupJobAPI()
        super(API, self).__init__(db_driver)

    def backupjob_get(self, context, backupjob_id):
        rv = self.db.backupjob_get(context, backupjob_id)
        return dict(rv.iteritems())

    def backupjob_show(self, context, backupjob_id):
        rv = self.db.backupjob_show(context, backupjob_id)
        return dict(rv.iteritems())
    
    def backupjob_get_all(self, context, search_opts={}):
        if context.is_admin:
            backupjobs = self.db.backupjob_get_all(context)
        else:
            backupjobs = self.db.backupjob_get_all_by_project(context,
                                                        context.project_id)

        return backupjobs
    
    def backupjob_create(self, context, name, description, instance_id,
               vault_service, hours=int(24), availability_zone=None):
        """
        Make the RPC call to create a backup job.
        """
        options = {'user_id': context.user_id,
                   'project_id': context.project_id,
                   'display_name': name,
                   'display_description': description,
                   'hours':hours,
                   'status': 'creating',
                   'vault_service': vault_service,
                   'host': socket.gethostname(), }

        backupjob = self.db.backupjob_create(context, options)

        #TODO(gbasava):  We will need to iterate thru the list of VMs when we support multiple VMs
        
        vminstance = {'backupjob_id': backupjob.id,
                      'vm_id': instance_id}
        vm = self.db.backupjob_vms_create(context, vminstance)
        
        self.backupjobs_rpcapi.backupjob_create(context,
                                         backupjob['host'],
                                         backupjob['id'])

        return backupjob
    
    def backupjob_delete(self, context, backupjob_id):
        """
        Make the RPC call to delete a backup job.
        """
        backup = self.backupjob_get(context, backupjob_id)
        if backup['status'] not in ['available', 'error']:
            msg = _('Backup status must be available or error')
            raise exception.InvalidBackupJob(reason=msg)

        self.db.backupjob_update(context, backupjob_id, {'status': 'deleting'})
        self.backupjobs_rpcapi.backupjob_delete(context,
                                         backup['host'],
                                         backup['id'])

    def backupjob_prepare(self, context, backupjob_id):
        """
        Make the RPC call to prepare a backup job.
        """
        backupjob = self.backupjob_get(context, backupjob_id)
        if backupjob['status'] in ['running']:
            msg = _('Backup job is already executing, ignoring this execution')
            raise exception.InvalidBackupJob(reason=msg)

        options = {'user_id': context.user_id,
                   'project_id': context.project_id,
                   'backupjob_id': backupjob_id,
                   'backuptype': 'full',
                   'status': 'creating',}
        backupjobrun = self.db.backupjobrun_create(context, options)
        self.backupjobs_rpcapi.backupjob_prepare(context, backupjob['host'], backupjobrun['id'])

    def backupjob_execute(self, context, backupjob_id):
        """
        Make the RPC call to execute a backup job.
        """
        backup = self.backupjob_get(context, backupjob_id)
        if backup['status'] in ['running']:
            msg = _('Backup job is already executing, ignoring this execution')
            raise exception.InvalidBackupJob(reason=msg)

        options = {'user_id': context.user_id,
                   'project_id': context.project_id,
                   'backupjob_id': backupjob_id,
                   'backuptype': 'incremental',
                   'status': 'creating',}
        backupjobrun = self.db.backupjobrun_create(context, options)
        self.backupjobs_rpcapi.backupjob_execute(context, backup['host'], backupjobrun['id'])

    def backupjobrun_get(self, context, backupjobrun_id):
        rv = self.db.backupjobrun_get(context, backupjobrun_id)
        return dict(rv.iteritems())

    def backupjobrun_show(self, context, backupjobrun_id):
        rv = self.db.backupjobrun_show(context, backupjobrun_id)
        return dict(rv.iteritems())
    
    def backupjobrun_get_all(self, context, backupjob_id=None):
        if backupjob_id:
             backupjobruns = self.db.backupjobrun_get_all_by_project_backupjob(
                                                    context,
                                                    context.project_id,
                                                    backupjob_id)
        elif context.is_admin:
            backupjobruns = self.db.backupjobrun_get_all(context)
        else:
            backupjobruns = self.db.backupjobrun_get_all_by_project(
                                        context,context.project_id)
        return backupjobruns
    
    def backupjobrun_delete(self, context, backupjobrun_id):
        """
        Make the RPC call to delete a backup jobrun.
        """
        backupjobrun = self.backupjobrun_get(context, backupjobrun_id)
        if backupjobrun['status'] not in ['available', 'error']:
            msg = _('Backupjobrun status must be available or error')
            raise exception.InvalidBackupJob(reason=msg)

        self.db.backupjobrun_update(context, backupjobrun_id, {'status': 'deleting'})
        self.backupjobs_rpcapi.backupjobrun_delete(context,
                                                   backupjobrun['id'])
    def backupjobrun_restore(self, context, backupjobrun_id):
        """
        Make the RPC call to restore a backup job run.
        """
        backupjobrun = self.backupjobrun_get(context, backupjobrun_id)
        backupjob = self.backupjob_get(context, backupjobrun['backupjob_id'])
        if backupjobrun['status'] != 'available':
            msg = _('Backupjobrun status must be available')
            raise exception.InvalidBackupJob(reason=msg)

        self.backupjobs_rpcapi.backupjobrun_restore(context, backupjob['host'], backupjobrun['id'])
        #TODO(gbasava): Return the restored instances

