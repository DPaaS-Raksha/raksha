# vim: tabstop=4 shiftwidth=4 softtabstop=4

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

import oslo.config.cfg

# Importing full names to not pollute the namespace and cause possible
# collisions with use of 'from raksha.volume import <foo>' elsewhere.
import raksha.openstack.common.importutils

_volume_opts = [
    oslo.config.cfg.StrOpt('volume_api_class',
                                     default='raksha.volume.cinder.API',
                                     help='The full class name of the '
                                          'volume API class to use'),
]

oslo.config.cfg.CONF.register_opts(_volume_opts)


def API():
    importutils = raksha.openstack.common.importutils
    volume_api_class = oslo.config.cfg.CONF.volume_api_class
    cls = importutils.import_class(volume_api_class)
    return cls()
