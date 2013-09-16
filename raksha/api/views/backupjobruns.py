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
    """Model backup job runs API responses as a python dictionary."""

    _collection_name = "backupjobruns"

    def __init__(self):
        """Initialize view builder."""
        super(ViewBuilder, self).__init__()

    def summary_list(self, request, backupjobruns):
        """Show a list of backupjobruns without many details."""
        return self._list_view(self.summary, request, backupjobruns)

    def detail_list(self, request, backupjobruns):
        """Detailed view of a list of backupjobruns ."""
        return self._list_view(self.detail, request, backupjobruns)

    def summary(self, request, backupjobrun):
        """Generic, non-detailed view of a backupjobrun."""
        return {
            'backupjobrun': {
                'id': backupjobrun['id'],
                'links': self._get_links(request,
                                         backupjobrun['id']),
            },
        }

    def restore_summary(self, request, restore):
        """Generic, non-detailed view of a restore."""
        return {
            'restore': {
                'backupjobrun_id': restore['backupjobrun_id'],
            },
        }

    def detail(self, request, backupjobrun):
        """Detailed view of a single backupjobrun."""
        return {
            'backupjobrun': {
                'created_at': backupjobrun.get('created_at'),
                'updated_at': backupjobrun.get('updated_at'),
                'id': backupjobrun.get('id'),
                'user_id': backupjobrun.get('user_id'),
                'project_id': backupjobrun.get('project_id'),
                'status': backupjobrun.get('status'),
                #'links': self._get_links(request, backupjobrun['id'],
                'name':  backupjobrun['id'],
            }
        }

    def _list_view(self, func, request, backupjobruns):
        """Provide a view for a list of backupjobruns."""
        backupjobruns_list = [func(request, backupjobrun)['backupjobrun'] for backupjobrun in backupjobruns]
        backupjobruns_links = self._get_collection_links(request,
                                                   backupjobruns,
                                                   self._collection_name)
        backupjobruns_dict = dict(backupjobruns=backupjobruns_list)

        if backupjobruns_links:
            backupjobruns_dict['backupjobruns_links'] = backupjobruns_links

        return backupjobruns_dict
