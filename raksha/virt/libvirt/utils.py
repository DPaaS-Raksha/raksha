# vim: tabstop=4 shiftwidth=4 softtabstop=4
#    Copyright 2010 United States Government as represented by the
#    Administrator of the National Aeronautics and Space Administration.
#    All Rights Reserved.
#    Copyright (c) 2010 Citrix Systems, Inc.
#    Copyright (c) 2011 Piston Cloud Computing, Inc
#    Copyright (c) 2011 OpenStack Foundation
#    (c) Copyright 2013 Hewlett-Packard Development Company, L.P.
#     Copyright (c) 2013 TrilioData
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


import os

from oslo.config import cfg
from raksha import exception
from raksha.openstack.common import log as logging
from raksha import utils
from raksha.virt import images

libvirt_opts = [

    ]

CONF = cfg.CONF
CONF.register_opts(libvirt_opts)
LOG = logging.getLogger(__name__)


def get_disk_backing_file(path, basename=True):
    """Get the backing file of a disk image

    :param path: Path to the disk image
    :returns: a path to the image's backing store
    """
    backing_file = images.qemu_img_info(path).backing_file
    if backing_file and basename:
        backing_file = os.path.basename(backing_file)

    return backing_file


