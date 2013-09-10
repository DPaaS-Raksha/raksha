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

"""The backupjobs api."""

import webob
from webob import exc
from xml.dom import minidom

from cgi import parse_qs, escape
from raksha.api import extensions
from raksha.api import wsgi
from raksha.api import common
from raksha.api.views import backupjobs as backupjob_views
from raksha.api import xmlutil
from raksha import backupjobs as backupjobAPI
from raksha import exception
from raksha import flags
from raksha.openstack.common import log as logging

FLAGS = flags.FLAGS
LOG = logging.getLogger(__name__)


def make_backupjob(elem):
    elem.set('id')
    elem.set('status')
    elem.set('size')
    elem.set('vault_service')
    elem.set('vm_id')
    elem.set('object_count')
    elem.set('availability_zone')
    elem.set('created_at')
    elem.set('name')
    elem.set('description')
    elem.set('fail_reason')



class BackupJobTemplate(xmlutil.TemplateBuilder):
    def construct(self):
        root = xmlutil.TemplateElement('backupjob', selector='backupjob')
        make_backupjob(root)
        alias = BackupJobs.alias
        namespace = BackupJobs.namespace
        return xmlutil.MasterTemplate(root, 1, nsmap={alias: namespace})


class BackupJobsTemplate(xmlutil.TemplateBuilder):
    def construct(self):
        root = xmlutil.TemplateElement('backupjobs')
        elem = xmlutil.SubTemplateElement(root, 'backupjob', selector='backupjobs')
        make_backupjob(elem)
        alias = BackupJobs.alias
        namespace = BackupJobs.namespace
        return xmlutil.MasterTemplate(root, 1, nsmap={alias: namespace})

class CreateDeserializer(wsgi.MetadataXMLDeserializer):
    def default(self, string):
        dom = minidom.parseString(string)
        backupjob = self._extract_backupjob(dom)
        return {'body': {'backupjob': backupjob}}

    def _extract_backupjob(self, node):
        backupjob = {}
        backupjob_node = self.find_first_child_named(node, 'backupjob')

        attributes = ['vault_service', 'display_name',
                      'display_description', 'instance_id']

        for attr in attributes:
            if backupjob_node.getAttribute(attr):
                backupjob[attr] = backupjob_node.getAttribute(attr)
        return backupjob

class BackupJobsController(wsgi.Controller):
    """The Backup Jobs API controller for the OpenStack API."""

    _view_builder_class = backupjob_views.ViewBuilder

    def __init__(self):
        self.backupjob_api = backupjobAPI.API()
        super(BackupJobsController, self).__init__()

    @wsgi.serializers(xml=BackupJobTemplate)
    def show(self, req, id):
        """Return data about the given backup job."""
        LOG.debug(_('show called for member %s'), id)
        context = req.environ['raksha.context']

        try:
            backupjob = self.backupjob_api.backupjob_show(context, backupjob_id=id)
        except exception.BackupJobNotFound as error:
            raise exc.HTTPNotFound(explanation=unicode(error))

        return self._view_builder.detail(req, backupjob)

    def delete(self, req, id):
        """Delete a backup job."""
        LOG.debug(_('delete called for member %s'), id)
        context = req.environ['raksha.context']

        LOG.audit(_('Delete backup with id: %s'), id, context=context)

        try:
            self.backupjob_api.backupjob_delete(context, id)
        except exception.BackupJobNotFound as error:
            raise exc.HTTPNotFound(explanation=unicode(error))
        except exception.InvalidBackupJob as error:
            raise exc.HTTPBadRequest(explanation=unicode(error))

        return webob.Response(status_int=202)

    def execute(self, req, id):
        """Execute a backup job."""
        LOG.debug(_('execute called for member %s'), id)
        context = req.environ['raksha.context']
        prepare = None;
        if ('QUERY_STRING' in req.environ) :
            qs=parse_qs(req.environ['QUERY_STRING'])
            var = parse_qs(req.environ['QUERY_STRING'])
            prepare = var.get('prepare',[''])[0]
            prepare = escape(prepare)

        LOG.audit(_('Execute an instance of backup id: %s'), id, context=context)
 
        try:
            if (prepare and prepare == '1'):
                self.backupjob_api.backupjob_prepare(context, id)
            else:
                self.backupjob_api.backupjob_execute(context, id)
        except exception.BackupJobNotFound as error:
            raise exc.HTTPNotFound(explanation=unicode(error))
        except exception.InvalidBackupJob as error:
            raise exc.HTTPBadRequest(explanation=unicode(error))

        return webob.Response(status_int=202)

    @wsgi.serializers(xml=BackupJobsTemplate)
    def index(self, req):
        """Returns a summary list of backups."""
        return self._get_backupjobs(req, is_detail=False)

    @wsgi.serializers(xml=BackupJobsTemplate)
    def detail(self, req):
        """Returns a detailed list of backupjobs."""
        return self._get_backupjobs(req, is_detail=True)

    def _get_backupjobs(self, req, is_detail):
        """Returns a list of backup jobs, transformed through view builder."""
        context = req.environ['raksha.context']
        backupjobs = self.backupjob_api.backupjob_get_all(context)
        limited_list = common.limited(backupjobs, req)

        if is_detail:
            backupjobs = self._view_builder.detail_list(req, limited_list)
        else:
            backupjobs = self._view_builder.summary_list(req, limited_list)
        return backupjobs

    @wsgi.response(202)
    @wsgi.serializers(xml=BackupJobTemplate)
    @wsgi.deserializers(xml=CreateDeserializer)
    def create(self, req, body):
        """Create a new backup job."""
        LOG.debug(_('Creating new backup job %s'), body)
        if not self.is_valid_body(body, 'backupjob'):
            raise exc.HTTPBadRequest()

        context = req.environ['raksha.context']

        try:
            backupjob = body['backupjob']
            instance_id = backupjob['instance_id']
        except KeyError:
            msg = _("Incorrect request body format")
            raise exc.HTTPBadRequest(explanation=msg)
        vault_service = backupjob.get('vault_service', None)
        name = backupjob.get('name', None)
        description = backupjob.get('description', None)
        hours = backupjob.get('hours', 24);

        LOG.audit(_("Creating backup job instance %(instance_id)s in vault_service"
                    " %(vault_service)s"), locals(), context=context)

        try:
            new_backup = self.backupjob_api.backupjob_create(context, name, 
                                          description, instance_id,
                                          vault_service, hours)
        except exception.InvalidVolume as error:
            raise exc.HTTPBadRequest(explanation=unicode(error))
        except exception.VolumeNotFound as error:
            raise exc.HTTPNotFound(explanation=unicode(error))

        retval = self._view_builder.summary(req, dict(new_backup.iteritems()))
        return retval


def create_resource():
    return wsgi.Resource(BackupJobsController())

