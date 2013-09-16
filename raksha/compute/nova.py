# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
#
# Copyright (c) 2013 TrilioData, Inc.
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
Handles all requests relating to compute + nova.
"""

import time

from novaclient import exceptions as nova_exception
from novaclient import service_catalog
from novaclient.v1_1 import client as nova_client
from oslo.config import cfg

from raksha.db import base
from raksha import exception
from raksha.openstack.common import log as logging

nova_opts = [
    cfg.StrOpt('nova_catalog_info',
            default='compute:nova:publicURL',
            help='Info to match when looking for nova in the service '
                 'catalog. Format is : separated values of the form: '
                 '<service_type>:<service_name>:<endpoint_type>'),
    cfg.StrOpt('nova_endpoint_template',
               default= 'http://localhost:8774/v2/%(project_id)s',
               help='Override service catalog lookup with template for nova '
                    'endpoint e.g. http://localhost:8774/v2/%(project_id)s'),
    cfg.StrOpt('os_region_name',
                default=None,
                help='region name of this node'),
    cfg.BoolOpt('nova_api_insecure',
               default=False,
               help='Allow to perform insecure SSL requests to nova'),
              
]

CONF = cfg.CONF
CONF.register_opts(nova_opts)

LOG = logging.getLogger(__name__)

    
def novaclient(context):

    compat_catalog = {
        # TODO(gbasava): Check this...   'access': {'serviceCatalog': context.service_catalog or []}
        'access': []
    }
    sc = service_catalog.ServiceCatalog(compat_catalog)
    if CONF.nova_endpoint_template:
        url = CONF.nova_endpoint_template % context.to_dict()
    else:
        info = CONF.nova_catalog_info
        service_type, service_name, endpoint_type = info.split(':')
        # extract the region if set in configuration
        if CONF.os_region_name:
            attr = 'region'
            filter_value = CONF.os_region_name
        else:
            attr = None
            filter_value = None
        url = sc.url_for(attr=attr,
                         filter_value=filter_value,
                         service_type=service_type,
                         service_name=service_name,
                         endpoint_type=endpoint_type)

    LOG.debug(_('Novaclient connection created using URL: %s') % url)

    c = nova_client.Client(context.user_id,
                           context.auth_token,
                           project_id=context.project_id,
                           auth_url=url,
                           insecure=CONF.nova_api_insecure)
    # noauth extracts user_id:tenant_id from auth_token
    c.client.auth_token = context.auth_token or '%s:%s' % (context.user_id,
                                                           context.project_id)
    c.client.management_url = url
    return c


class API(base.Base):
    """API for interacting with the volume manager."""

    def create_server(self, context, name, image, flavor, 
               meta=None, files=None,
               reservation_id=None, min_count=None,
               max_count=None, security_groups=None, userdata=None,
               key_name=None, availability_zone=None,
               block_device_mapping=None, nics=None, scheduler_hints=None,
               config_drive=None, **kwargs):

        """
        Create (boot) a new server.

        :param name: Something to name the server.
        :param image: The :class:`Image` to boot with.
        :param flavor: The :class:`Flavor` to boot onto.
        :param meta: A dict of arbitrary key/value metadata to store for this
                     server. A maximum of five entries is allowed, and both
                     keys and values must be 255 characters or less.
        :param files: A dict of files to overrwrite on the server upon boot.
                      Keys are file names (i.e. ``/etc/passwd``) and values
                      are the file contents (either as a string or as a
                      file-like object). A maximum of five entries is allowed,
                      and each file must be 10k or less.
        :param userdata: user data to pass to be exposed by the metadata
                      server this can be a file type object as well or a
                      string.
        :param reservation_id: a UUID for the set of servers being requested.
        :param key_name: (optional extension) name of previously created
                      keypair to inject into the instance.
        :param availability_zone: Name of the availability zone for instance
                                  placement.
        :param block_device_mapping: (optional extension) A dict of block
                      device mappings for this server.
        :param nics:  (optional extension) an ordered list of nics to be
                      added to this server, with information about
                      connected networks, fixed ips, port etc.
        :param scheduler_hints: (optional extension) arbitrary key-value pairs
                            specified by the client to help boot an instance
        :param config_drive: (optional extension) value for config drive
                            either boolean, or volume-id
        """
        
        try:
            item = novaclient(context).servers.create(name, image, flavor, 
                                                      meta, files,
                                                      reservation_id, min_count,
                                                      max_count, security_groups, userdata,
                                                      key_name, availability_zone,
                                                      block_device_mapping, nics, scheduler_hints,
                                                      config_drive, **kwargs)
            time.sleep(15)#TODO(gbasava): Creation is asynchronous. Wait and check for the status
            #Perform translation required if any
            return item 
        except Exception:
            #TODO(gbasava): Handle the exception 
            return       
            
    def get_server(self, context, name):
        """
        Get the server given the name

        :param name: name of the image
        :rtype: :class:`Server`
        """   
    
        try:
            return novaclient(context).servers.find(name=name) 
        except Exception:
            #TODO(gbasava): Handle the exception 
            return 
                    
    def attach_volume(self, context, server_id, volume_id, device):
        """
        Attach a volume identified by the volume ID to the given server ID

        :param server_id: The ID of the server
        :param volume_id: The ID of the volume to attach.
        :param device: The device name
        :rtype: :class:`Volume`
        """   
  
        try:
            return novaclient(context).volumes.create_server_volume(server_id, volume_id, device) 
        except Exception:
            #TODO(gbasava): Handle the exception   
            return 
                    
    def get_image(self, context, id):
        """
        Get the image given the name

        :param name: name of the image
        :rtype: :class:`Image`
        """   
    
        try:
            return novaclient(context).images.find(id=id) 
        except Exception:
            #TODO(gbasava): Handle the exception 
            return 
                      
    def get_flavor(self, context, name):
        """
        Get the flavors given the name

        :param name: name of the flavors
        :rtype: :class:`Flavor`
        """   
    
        try:
            return novaclient(context).flavors.find(name=name) 
        except Exception:
            #TODO(gbasava): Handle the exception   
            return                                        