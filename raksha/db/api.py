# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2013 TrilioData, Inc.
# Copyright (c) 2011 X.commerce, a business unit of eBay Inc.
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

"""Defines interface for DB access.

The underlying driver is loaded as a :class:`LazyPluggable`.

Functions in this module are imported into the raksha.db namespace. Call these
functions from raksha.db namespace, not the raksha.db.api namespace.

All functions in this module return objects that implement a dictionary-like
interface. Currently, many of these objects are sqlalchemy objects that
implement a dictionary interface. However, a future goal is to have all of
these objects be simple dictionaries.


**Related Flags**

:db_backend:  string to lookup in the list of LazyPluggable backends.
              `sqlalchemy` is the only supported backend right now.

:sql_connection:  string specifying the sqlalchemy connection to use, like:
                  `sqlite:///var/lib/raksha/raksha.sqlite`.

:enable_new_services:  when adding a new service to the database, is it in the
                       pool of available hardware (Default: True)

"""

from oslo.config import cfg

from raksha import exception
from raksha import flags
from raksha import utils

db_opts = [
    cfg.StrOpt('db_backend',
               default='sqlalchemy',
               help='The backend to use for db'),
    cfg.BoolOpt('enable_new_services',
                default=True,
                help='Services to be added to the available pool on create'),
    cfg.StrOpt('backupjob_name_template',
               default='backupjob-%s',
               help='Template string to be used to generate backup job names'), ]

FLAGS = flags.FLAGS
FLAGS.register_opts(db_opts)

IMPL = utils.LazyPluggable('db_backend',
                           sqlalchemy='raksha.db.sqlalchemy.api')


class NoMoreTargets(exception.RakshaException):
    """No more available targets"""
    pass


###################


def service_destroy(context, service_id):
    """Destroy the service or raise if it does not exist."""
    return IMPL.service_destroy(context, service_id)


def service_get(context, service_id):
    """Get a service or raise if it does not exist."""
    return IMPL.service_get(context, service_id)


def service_get_by_host_and_topic(context, host, topic):
    """Get a service by host it's on and topic it listens to."""
    return IMPL.service_get_by_host_and_topic(context, host, topic)


def service_get_all(context, disabled=None):
    """Get all services."""
    return IMPL.service_get_all(context, disabled)


def service_get_all_by_topic(context, topic):
    """Get all services for a given topic."""
    return IMPL.service_get_all_by_topic(context, topic)


def service_get_all_by_host(context, host):
    """Get all services for a given host."""
    return IMPL.service_get_all_by_host(context, host)


def service_get_all_volume_sorted(context):
    """Get all volume services sorted by volume count.

    :returns: a list of (Service, volume_count) tuples.

    """
    return IMPL.service_get_all_volume_sorted(context)


def service_get_by_args(context, host, binary):
    """Get the state of an service by node name and binary."""
    return IMPL.service_get_by_args(context, host, binary)


def service_create(context, values):
    """Create a service from the values dictionary."""
    return IMPL.service_create(context, values)


def service_update(context, service_id, values):
    """Set the given properties on an service and update it.

    Raises NotFound if service does not exist.

    """
    return IMPL.service_update(context, service_id, values)


###################


def backupjob_get(context, backupjob_id):
    """Get a backupjob or raise if it does not exist."""
    return IMPL.backupjob_get(context, backupjob_id)

def backupjob_show(context, backupjob_id):
    """Get more details of the  backupjob or raise if it does not exist."""
    return IMPL.backupjob_show(context, backupjob_id)

def backupjob_get_all(context):
    """Get all backup jobs."""
    return IMPL.backupjob_get_all(context)


def backupjob_get_all_by_host(context, host):
    """Get all backupjobs belonging to a host."""
    return IMPL.backupjob_get_all_by_host(context, host)


def backupjob_create(context, values):
    """Create a backup job from the values dictionary."""
    return IMPL.backupjob_create(context, values)


def backupjob_get_all_by_project(context, project_id):
    """Get all backups belonging to a project."""
    return IMPL.backupjob_get_all_by_project(context, project_id)


def backupjob_update(context, backupjob_id, values):
    """
    Set the given properties on a backupjob  and update it.

    Raises NotFound if backupjob  does not exist.
    """
    return IMPL.backupjob_update(context, backupjob_id, values)


def backupjob_destroy(context, backupjob_id):
    """Destroy the backup job or raise if it does not exist."""
    return IMPL.backupjob_destroy(context, backupjob_id)

def backupjob_vms_create(context, values):
    return IMPL.backupjob_vms_create(context, values)

def backupjob_vms_get(context, backupjob_id, session=None):
    return IMPL.backupjob_vms_get(context, backupjob_id, session)

def backupjob_vms_destroy(context, vm_id, backupjob_id):
    return IMPL.backupjob_vms_destroy(context, vm_id, backupjob_id)
    
def scheduledjob_create(context, scheduledjob):
    return IMPL.scheduledjob_create(context, scheduledjob)

def scheduledjob_delete(context, scheduledjob):
    return IMPL.scheduledjob_delete(context, scheduledjob)

def scheduledjob_get(context):
    return IMPL.scheduledjob_get(context)

def scheduledjob_update(context, scheduledjob):
    return IMPL.scheduledjob_update(context, scheduledjob)

def backupjobrun_create(context, values):
    return IMPL.backupjobrun_create(context, values)

def backupjobrun_get(context, backupjobrun_id, session=None):
    return IMPL.backupjobrun_get(context, backupjobrun_id, session)
    
def backupjobrun_get_all(context, backupjob_id=None):
    return IMPL.backupjobrun_get_all(context, backupjob_id)    

def backupjobrun_get_all_by_project(context, project_id):
    """Get all backups belonging to a project."""
    return IMPL.backupjobrun_get_all_by_project(context, project_id)
    
def backupjobrun_get_all_by_project_backupjob(context, project_id, backupjob_id):
    """Get all backups belonging to a project and backupjob"""
    return IMPL.backupjobrun_get_all_by_project_backupjob(context, project_id, backupjob_id)
    
def backupjobrun_show(context, backupjobrun_id):
    """Get more details of the  backupjobrun or raise if it does not exist."""
    return IMPL.backupjobrun_show(context, backupjobrun_id)

def backupjobrun_update(context, backupjobrun_id, values):
    return IMPL.backupjobrun_update(context, backupjobrun_id, values)

def backupjobrun_vm_create(context, values):
    return IMPL.backupjobrun_vm_create(context, values)

def backupjobrun_vm_get(context, backupjobrun_id, session=None):
    return IMPL.backupjobrun_vm_get(context, backupjobrun_id, session)

def backupjobrun_vm_destroy(context, vm_id, backupjobrun_id):
    return IMPL.backupjobrun_vm_destroy(context, vm_id, backupjobrun_id)

def vm_recent_backupjobrun_create(context, values):
    return IMPL.vm_recent_backupjobrun_create(context, values)

def vm_recent_backupjobrun_get(context, vm_id, session=None):
    return IMPL.vm_recent_backupjobrun_get(context, vm_id, session)

def vm_recent_backupjobrun_update(context, vm_id, values):
    return IMPL.vm_recent_backupjobrun_update(context, vm_id, values)

def vm_recent_backupjobrun_destroy(context, vm_id):
    return IMPL.vm_recent_backupjobrun_destroy(context, vm_id)

def backupjobrun_vm_resource_create(context, values):
    return IMPL.backupjobrun_vm_resource_create(context, values)

def backupjobrun_vm_resources_get(context, vm_id, backupjobrun_id, session=None):
    return IMPL.backupjobrun_vm_resources_get(context, vm_id, backupjobrun_id, session)

def backupjobrun_vm_resource_get(context, vm_id, backupjobrun_id, resource_name, session=None):
    return IMPL.backupjobrun_vm_resource_get(context, vm_id, backupjobrun_id, resource_name, session)

def backupjobrun_vm_resource_get2(context, id, session=None):
    return IMPL.backupjobrun_vm_resource_get2(context, id, session)

def backupjobrun_vm_resource_destroy(context, id, vm_id, backupjobrun_id):
    return IMPL.backupjobrun_vm_resource_destroy(context, id, vm_id, backupjobrun_id)
    
def vm_resource_backup_create(context, values):
    return IMPL.vm_resource_backup_create(context, values)

def vm_resource_backups_get(context, backupjobrun_vm_resource_id, session=None):
    return IMPL.vm_resource_backups_get(context, backupjobrun_vm_resource_id, session)

def vm_resource_backup_get_top(context, backupjobrun_vm_resource_id, session=None):
    return IMPL.vm_resource_backup_get_top(context, backupjobrun_vm_resource_id, session)

def vm_resource_backup_get(context, vm_resource_backup_id, session=None):
    return IMPL.vm_resource_backup_get(context, vm_resource_backup_id, session)

def vm_resource_backups_destroy(context, backupjobrun_vm_resource_id):
    return IMPL.vm_resource_backups_destroy(context, backupjobrun_vm_resource_id)
    
def vault_service_create(context, values):
    return IMPL.vault_service_create(context, values)

def vault_service_get(context, id, session=None):
    return IMPL.vault_service_get(context, id, session)

def vault_service_destroy(context, id):
    return IMPL.vault_service_destroy(context, id)    