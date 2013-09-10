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

# Importing full names to not pollute the namespace and cause possible
# collisions with use of 'from raksha.backup import <foo>' elsewhere.

import raksha.flags
import raksha.openstack.common.importutils

API = raksha.openstack.common.importutils.import_class(
        raksha.flags.FLAGS.backupjobs_api_class)
