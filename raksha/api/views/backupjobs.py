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

from raksha.openstack.common import log as logging
from raksha.api import common


LOG = logging.getLogger(__name__)


class ViewBuilder(common.ViewBuilder):
    """Model backup job API responses as a python dictionary."""

    _collection_name = "backupjobs"

    def __init__(self):
        """Initialize view builder."""
        super(ViewBuilder, self).__init__()

    def summary_list(self, request, backupjobs):
        """Show a list of backupjobs without many details."""
        return self._list_view(self.summary, request, backupjobs)

    def detail_list(self, request, backupjobs):
        """Detailed view of a list of backupjobs ."""
        return self._list_view(self.detail, request, backupjobs)

    def summary(self, request, backupjob):
        """Generic, non-detailed view of a backupjob."""
        return {
            'backupjob': {
                'id': backupjob['id'],
                'name': backupjob['display_name'],
                'links': self._get_links(request,
                                         backupjob['id']),
            },
        }

    def restore_summary(self, request, restore):
        """Generic, non-detailed view of a restore."""
        return {
            'restore': {
                'backupjob_id': restore['backupjob_id'],
                'instance_id': restore['instance_id'],
            },
        }

    def detail(self, request, backupjob):
        """Detailed view of a single backupjob."""
        return {
            'backupjob': {
                'created_at': backupjob.get('created_at'),
                'updated_at': backupjob.get('updated_at'),
                'id': backupjob.get('id'),
                'user_id': backupjob.get('user_id'),
                'project_id': backupjob.get('project_id'),
                'host': backupjob.get('host'),
                'availability_zone': backupjob.get('availability_zone'),
                'vault_service': backupjob.get('vault_service'),
                'name': backupjob.get('display_name'),
                'description': backupjob.get('display_description'),
                'interval': backupjob.get('hours'),
                'status': backupjob.get('status'),
                'links': self._get_links(request, backupjob['id'])
            }
        }

    def _list_view(self, func, request, backupjobs):
        """Provide a view for a list of backupjobs."""
        backupjobs_list = [func(request, backupjob)['backupjob'] for backupjob in backupjobs]
        backupjobs_links = self._get_collection_links(request,
                                                   backupjobs,
                                                   self._collection_name)
        backupjobs_dict = dict(backupjobs=backupjobs_list)

        if backupjobs_links:
            backupjobs_dict['backupjobs_links'] = backupjobs_links

        return backupjobs_dict
