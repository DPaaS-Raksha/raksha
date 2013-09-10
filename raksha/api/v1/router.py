# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
# Copyright 2011 United States Government as represented by the
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

"""
WSGI middleware for OpenStack backup jobs API.
"""

from raksha.api import extensions
from raksha.api import versions
import raksha.api
from raksha.openstack.common import log as logging
from raksha.api.v1 import backupjobs
from raksha.api.v1 import backupjobruns

LOG = logging.getLogger(__name__)


class APIRouter(raksha.api.APIRouter):
    """
    Routes requests on the OpenStack API to the appropriate controller
    and method.
    """
    ExtensionManager = extensions.ExtensionManager

    def _setup_routes(self, mapper, ext_mgr):
        self.resources['versions'] = versions.create_resource()
        mapper.connect("versions", "/",
                       controller=self.resources['versions'],
                       action='show')

        mapper.redirect("", "/")

        self.resources['backupjobs'] = backupjobs.create_resource()
        mapper.resource("backupjob", "backupjobs",
                        controller=self.resources['backupjobs'],
                        collection={'detail': 'GET'},
                        member={'action': 'POST'})
        
        mapper.connect("execute",
                       "/{project_id}/backupjobs/{id}",
                       controller=self.resources['backupjobs'],
                       action='execute',
                       conditions={"method": ['POST']})

        self.resources['backupjobruns'] = backupjobruns.create_resource(ext_mgr)
        mapper.resource("backupjobrun", "backupjobruns",
                        controller=self.resources['backupjobruns'],
                        collection={'detail': 'GET'},
                        member={'action': 'POST'})  
        
        mapper.connect("restore",
               "/{project_id}/backupjobruns/{id}",
               controller=self.resources['backupjobruns'],
               action='restore',
               conditions={"method": ['POST']})      