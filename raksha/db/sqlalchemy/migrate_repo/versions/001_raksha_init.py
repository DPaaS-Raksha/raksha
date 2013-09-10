# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2013 TrilioData, Inc.
# Copyright 2012 OpenStack LLC.
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

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Text
from sqlalchemy import Integer, MetaData, String, Table, UniqueConstraint
import sqlalchemy

import pickle
from raksha import flags
from raksha.openstack.common import log as logging

FLAGS = flags.FLAGS

LOG = logging.getLogger(__name__)


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine

    #pickle_coltype = PickleType(pickle.HIGHEST_PROTOCOL)

    services = Table(
        'services', meta,
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
        Column('deleted_at', DateTime),
        Column('deleted', Boolean),
        Column('id', Integer, primary_key=True, nullable=False),
        Column('host', String(length=255)),
        Column('binary', String(length=255)),
        Column('topic', String(length=255)),
        Column('report_count', Integer, nullable=False),
        Column('disabled', Boolean),
        Column('availability_zone', String(length=255)),
        mysql_engine='InnoDB'
    )

    vault_services = Table(
        'vault_services', meta,
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
        Column('deleted_at', DateTime),
        Column('deleted', Boolean),
        Column('id', String(length=255), primary_key=True, nullable= False),
        Column('service_name', String(length=255)),
        mysql_engine='InnoDB'
    )   
    
      
    backupjobs = Table(
        'backupjobs', meta,
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
        Column('deleted_at', DateTime),
        Column('deleted', Boolean),
        Column('id', String(length=255), primary_key=True, nullable=False),
        Column('user_id', String(length=255)),
        Column('project_id', String(length=255)),
        Column('host', String(length=255)),
        Column('availability_zone', String(length=255)),
        Column('display_name', String(length=255)),
        Column('display_description', String(length=255)),
        Column('vault_service', String(length=255)),
        Column('status', String(length=255)),
        mysql_engine='InnoDB'
    )
  
    backupjob_vms = Table(
        'backupjob_vms', meta,
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
        Column('deleted_at', DateTime),
        Column('deleted', Boolean),
        Column('id', String(length=255), primary_key=True, nullable= False),
        Column('vm_id', String(length=255), nullable= False),
        Column('backupjob_id', String(length=255), ForeignKey('backupjobs.id')),
        mysql_engine='InnoDB'
    )

    scheduled_jobs = Table(
        'scheduled_jobs', meta,
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
        Column('deleted_at', DateTime),
        Column('deleted', Boolean),
        Column('id', String(length=255), primary_key=True),
        Column('backupjob_id', String(length=255), ForeignKey('backupjobs.id')),
        Column('trigger', String(length=4096), nullable=False),
        Column('func_ref', String(length=1024), nullable=False),
        Column('args', String(length=1024), nullable=False),
        Column('kwargs', String(length=1024), nullable=False),
        Column('name', String(length=1024)),
        Column('misfire_grace_time', Integer, nullable=False),
        Column('coalesce', Boolean, nullable=False),
        Column('max_runs', Integer),
        Column('max_instances', Integer),
        Column('next_run_time', DateTime, nullable=False),
        Column('runs', Integer), mysql_engine='InnoDB')
        
    backupjobruns = Table(
        'backupjobruns', meta,
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
        Column('deleted_at', DateTime),
        Column('deleted', Boolean),
        Column('id', String(length=255), primary_key=True, nullable= False),
        Column('backupjob_id', String(length=255), ForeignKey('backupjobs.id')),
        Column('user_id', String(length=255)),
        Column('project_id', String(length=255)),
        Column('backuptype', String(length=32), primary_key=False, nullable= False),
        Column('status', String(length=32), nullable=False),
        mysql_engine='InnoDB'
    )
    
    backupjobrun_vms = Table(
        'backupjobrun_vms', meta,
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
        Column('deleted_at', DateTime),
        Column('deleted', Boolean),
        Column('id', String(length=255), primary_key=True, nullable= False),
        Column('vm_id', String(length=255), nullable= False),
        Column('backupjobrun_id', String(length=255), ForeignKey('backupjobruns.id')),
        Column('status', String(length=32), nullable=False),
        mysql_engine='InnoDB'
    )
    
    vm_recent_backupjobrun  = Table(
        'vm_recent_backupjobrun', meta,
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
        Column('deleted_at', DateTime),
        Column('deleted', Boolean),
        Column('vm_id', String(length=255), primary_key=True, nullable= False),
        Column('backupjobrun_id', String(length=255), ForeignKey('backupjobruns.id')),
        mysql_engine='InnoDB'
    )    
    
    backupjobrun_vm_resources = Table(
        'backupjobrun_vm_resources', meta,
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
        Column('deleted_at', DateTime),
        Column('deleted', Boolean),
        Column('id', String(length=255), primary_key=True, nullable= False),
        Column('vm_id', String(length=255), nullable= False),
        Column('backupjobrun_id', String(length=255), ForeignKey('backupjobruns.id')),
        Column('resource_name', String(length=255)),
        Column('resource_type', String(length=255)),
        Column('status', String(length=32), nullable=False),
        UniqueConstraint('vm_id', 'backupjobrun_id', 'resource_name'),
        mysql_engine='InnoDB'
    )
    
    vm_resource_backups = Table(
        'vm_resource_backups', meta,
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
        Column('deleted_at', DateTime),
        Column('deleted', Boolean),
        Column('id', String(length=255), primary_key=True, nullable= False),
        Column('backupjobrun_vm_resource_id', String(length=255), ForeignKey('backupjobrun_vm_resources.id')),
        Column('vm_resource_backup_backing_id', String(length=255), ForeignKey('vm_resource_backups.id')),
        Column('top', Boolean, default=False),
        Column('vault_service_id', String(255)),
        Column('vault_service_url', String(4096)),    
        Column('vault_service_metadata', String(4096)),         
        Column('status', String(length=32), nullable=False),
        mysql_engine='InnoDB'
    )        
    
    vm_resource_backup_metadata = Table(
        'vm_resource_backup_metadata', meta,
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
        Column('deleted_at', DateTime),
        Column('deleted', Boolean),
        Column('id', String(length=255), primary_key=True, nullable= False),
        Column('vm_resource_backup_id', String(length=255), ForeignKey('vm_resource_backups.id'),nullable=False,index=True),        
        Column('key', String(255), nullable=False),
        Column('value', Text()),
        UniqueConstraint('vm_resource_backup_id', 'key'),
        mysql_engine='InnoDB'
    )        
        
   
    # create all tables
    # Take care on create order for those with FK dependencies
    tables = [services,
              vault_services,
              backupjobs,
              backupjob_vms,
              scheduled_jobs,
              backupjobruns,
              backupjobrun_vms,
              vm_recent_backupjobrun,
              backupjobrun_vm_resources,
              vm_resource_backups,
              vm_resource_backup_metadata]

    for table in tables:
        try:
            table.create()
        except Exception:
            LOG.info(repr(table))
            LOG.exception(_('Exception while creating table.'))
            raise

    if migrate_engine.name == "mysql":
        tables = ["services",
                  "vault_services",
                  "backupjobs",
                  "backupjob_vms",
                  "scheduled_jobs",
                  "backupjobruns",
                  "backupjobrun_vms",
                  "vm_recent_backupjobrun",
                  "backupjobrun_vm_resources",
                  "vm_resource_backups",
                  "vm_resource_backup_metadata"]

        sql = "SET foreign_key_checks = 0;"
        for table in tables:
            sql += "ALTER TABLE %s CONVERT TO CHARACTER SET utf8;" % table
        sql += "SET foreign_key_checks = 1;"
        sql += "ALTER DATABASE %s DEFAULT CHARACTER SET utf8;" \
            % migrate_engine.url.database
        sql += "ALTER TABLE %s Engine=InnoDB;" % table
        migrate_engine.execute(sql)


def downgrade(migrate_engine):
    LOG.exception(_('Downgrade from initial Raksha install is unsupported.'))
