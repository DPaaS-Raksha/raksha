# vim: tabstop=4 shiftwidth=4 softtabstop=4

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
Client side of the backup job scheduler RPC API.
"""

from raksha import flags
from raksha.openstack.common import log as logging
from raksha.openstack.common import rpc
import raksha.openstack.common.rpc.proxy


LOG = logging.getLogger(__name__)

FLAGS = flags.FLAGS


class BackupJobAPI(raksha.openstack.common.rpc.proxy.RpcProxy):
    '''Client side of the raksha rpc API.

    API version history:

        1.0 - Initial version.
    '''

    BASE_RPC_API_VERSION = '1.0'

    def __init__(self):
        super(BackupJobAPI, self).__init__(
            topic=FLAGS.backupjobs_topic,
            default_version=self.BASE_RPC_API_VERSION)

    def backupjob_create(self, ctxt, host, backupjob_id):
        LOG.debug("create_backup job in rpcapi backup_id %s", backupjob_id)
        topic = rpc.queue_get_for(ctxt, self.topic, host)
        LOG.debug("create queue topic=%s", topic)
        self.cast(ctxt,
                  self.make_msg('backupjob_create',
                                backupjob_id=backupjob_id),
                  topic=topic)

    def backupjob_execute(self, ctxt, host, backupjobrun_id):
        LOG.debug("execute_backup job in rpcapi backupjobrun_id %s", backupjobrun_id)
        topic = rpc.queue_get_for(ctxt, self.topic, host)
        LOG.debug("create queue topic=%s", topic)
        self.cast(ctxt,
                  self.make_msg('backupjob_execute',
                                backupjobrun_id=backupjobrun_id),
                  topic=topic)

    def backupjob_prepare(self, ctxt, host, backupjobrun_id):
        LOG.debug("prepare_backup job in rpcapi backupjobrun_id %s", backupjobrun_id)
        topic = rpc.queue_get_for(ctxt, self.topic, host)
        LOG.debug("create queue topic=%s", topic)
        self.cast(ctxt,
                  self.make_msg('backupjob_prepare',
                                backupjobrun_id=backupjobrun_id),
                  topic=topic)

    def backupjob_delete(self, ctxt, host, backupjob_id):
        LOG.debug("delete_backupjob  rpcapi backupjob_id %s", backupjob_id)
        topic = rpc.queue_get_for(ctxt, self.topic, host)
        self.cast(ctxt,
                  self.make_msg('backupjob_delete', backupjob_id=backupjob_id),
                  topic=topic)

    def backupjobrun_restore(self, ctxt, host, backupjobrun_id):
        LOG.debug("restore_backup in rpcapi backupjobrun_id %s", 
                              backupjobrun_id)
        topic = rpc.queue_get_for(ctxt, self.topic, host)
        LOG.debug("restore queue topic=%s", topic)
        self.cast(ctxt,
                  self.make_msg('backupjobrun_restore',backupjobrun_id=backupjobrun_id),
                  topic=topic)
        
    def backupjobrun_delete(self, ctxt, host, backupjobrun_id):
        LOG.debug("delete_backupinstance  rpcapi backupjobrun_id %s", 
                        backupjobrun_id)
        topic = rpc.queue_get_for(ctxt, self.topic, host)
        self.cast(ctxt,
                  self.make_msg('backupjobrun_delete',backupjobrun_id=backupjobrun_id),
                  topic=topic)
