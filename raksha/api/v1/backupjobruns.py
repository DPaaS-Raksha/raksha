# Copyright 2011 Justin Santa Barbara
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

"""The backupjobruns api."""

import webob
from webob import exc
from xml.dom import minidom

from raksha.api import common
from raksha.api import wsgi
from raksha.api import xmlutil
from raksha import exception
from raksha import flags
from raksha.openstack.common import log as logging
from raksha.openstack.common import strutils
from raksha import utils
from raksha import backupjobs as backupjobAPI
from raksha.api.views import backupjobruns as backupjobrun_views


LOG = logging.getLogger(__name__)


FLAGS = flags.FLAGS


def _translate_backupjobrun_detail_view(context, backupjobrun):
    """Maps keys for backupjobruns details view."""

    d = _translate_backupjobrun_summary_view(context, backupjobrun)

    return d


def _translate_backupjobrun_summary_view(context, backupjobrun):
    """Maps keys for backupjobruns summary view."""
    d = {}

    d['id'] = backupjobrun['id']
    d['created_at'] = backupjobrun['created_at']
    d['status'] = backupjobrun['status']
 
    return d


def make_backupjobrun(elem):
    elem.set('id')
    elem.set('status')
    elem.set('created_at')
    elem.set('name')
    elem.set('description')
    


class BackupJobRunTemplate(xmlutil.TemplateBuilder):
    def construct(self):
        root = xmlutil.TemplateElement('backupjobrun', selector='backupjobrun')
        make_backupjobrun(root)
        return xmlutil.MasterTemplate(root, 1)


class BackupJobRunsTemplate(xmlutil.TemplateBuilder):
    def construct(self):
        root = xmlutil.TemplateElement('backupjobruns')
        elem = xmlutil.SubTemplateElement(root, 'backupjobrun',
                                          selector='backupjobruns')
        make_backupjobrun(elem)
        return xmlutil.MasterTemplate(root, 1)

def make_backupjobrun_restore(elem):
    elem.set('backupjobrun_id')
    
class BackupJobRunRestoreTemplate(xmlutil.TemplateBuilder):
    def construct(self):
        root = xmlutil.TemplateElement('restore', selector='restore')
        make_backupjobrun_restore(root)
        alias = BackupJobRuns.alias
        namespace = BackupJobRuns.namespace
        return xmlutil.MasterTemplate(root, 1, nsmap={alias: namespace})

class RestoreDeserializer(wsgi.MetadataXMLDeserializer):
    def default(self, string):
        dom = minidom.parseString(string)
        restore = self._extract_restore(dom)
        return {'body': {'restore': restore}}

    def _extract_restore(self, node):
        restore = {}
        restore_node = self.find_first_child_named(node, 'restore')
        if restore_node.getAttribute('backupjobrun_id'):
            restore['backupjobrun_id'] = restore_node.getAttribute('backupjobrun_id')
        return restore


class BackupJobRunsController(wsgi.Controller):
    """The backupjobruns API controller for the OpenStack API."""

    _view_builder_class = backupjobrun_views.ViewBuilder
    
    def __init__(self, ext_mgr=None):
        self.backupjob_api = backupjobAPI.API()
        self.ext_mgr = ext_mgr
        super(BackupJobRunsController, self).__init__()

    @wsgi.serializers(xml=BackupJobRunTemplate)
    def show(self, req, id):
        """Return data about the given BackupJobRun."""
        context = req.environ['raksha.context']

        try:
            backupjobrun = self.backupjob_api.backupjobrun_show(context, id)
        except exception.NotFound:
            raise exc.HTTPNotFound()

        return {'backupjobrun': _translate_backupjobrun_detail_view(context, backupjobrun)}

    def delete(self, req, id):
        """Delete a backupjobrun."""
        context = req.environ['raksha.context']

        LOG.audit(_("Delete backupjobrun with id: %s"), id, context=context)

        try:
            backupjobrun = self.backupjob_api.backupjobrun_get(context, id)
            self.backupjob_api.deletebackupjobrun(context, backupjobrun)
        except exception.NotFound:
            raise exc.HTTPNotFound()
        return webob.Response(status_int=202)

    @wsgi.serializers(xml=BackupJobRunsTemplate)
    def index(self, req):
        """Returns a summary list of backupjobruns."""
        return self._get_backupjobruns(req, is_detail=False)

    @wsgi.serializers(xml=BackupJobRunsTemplate)
    def detail(self, req):
        """Returns a detailed list of backupjobruns."""
        return self._get_backupjobruns(req, is_detail=True)

    def _get_backupjobruns(self, req, is_detail):
        """Returns a list of backup job runs, transformed through view builder."""
        context = req.environ['raksha.context']
        backupjob_id = req.GET.get('backupjob_id', None)
        if backupjob_id:
            backupjobruns = self.backupjob_api.backupjobrun_get_all(context, backupjob_id)
        else:
            backupjobruns = self.backupjob_api.backupjobrun_get_all(context)
   
        limited_list = common.limited(backupjobruns, req)

        if is_detail:
            backupjobruns = self._view_builder.detail_list(req, limited_list)
        else:
            backupjobruns = self._view_builder.summary_list(req, limited_list)
        return backupjobruns
    
    @wsgi.response(202)
    @wsgi.serializers(xml=BackupJobRunRestoreTemplate)
    @wsgi.deserializers(xml=RestoreDeserializer)
    def restore(self, req, id):
        """Restore an existing backupjobrun"""
        backupjobrun_id = id
        LOG.debug(_('Restoring backupjobrun %(backupjobrun_id)s') % locals())
        context = req.environ['raksha.context']
        LOG.audit(_("Restoring backupjobrun %(backupjobrun_id)s"),
                  locals(), context=context)

        try:
            self.backupjob_api.backupjobrun_restore(context, backupjobrun_id = backupjobrun_id )
        except exception.InvalidInput as error:
            raise exc.HTTPBadRequest(explanation=unicode(error))
        except exception.InvalidVolume as error:
            raise exc.HTTPBadRequest(explanation=unicode(error))
        except exception.InvalidBackupJob as error:
            raise exc.HTTPBadRequest(explanation=unicode(error))
        except exception.BackupJobNotFound as error:
            raise exc.HTTPNotFound(explanation=unicode(error))
        except exception.VolumeNotFound as error:
            raise exc.HTTPNotFound(explanation=unicode(error))
        except exception.VolumeSizeExceedsAvailableQuota as error:
            raise exc.HTTPRequestEntityTooLarge(
                explanation=error.message, headers={'Retry-After': 0})
        except exception.VolumeLimitExceeded as error:
            raise exc.HTTPRequestEntityTooLarge(
                explanation=error.message, headers={'Retry-After': 0})

        return webob.Response(status_int=202)


def create_resource(ext_mgr):
    return wsgi.Resource(BackupJobRunsController(ext_mgr))
