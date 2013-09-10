# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2013 TrilioData, Inc.
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

"""Raksha base exception handling.

Includes decorator for re-raising Raksha-type exceptions.

SHOULD include dedicated exception logging.

"""

from oslo.config import cfg
import webob.exc

from raksha import flags
from raksha.openstack.common import log as logging

LOG = logging.getLogger(__name__)

exc_log_opts = [
    cfg.BoolOpt('fatal_exception_format_errors',
                default=False,
                help='make exception message format errors fatal'),
]

FLAGS = flags.FLAGS
FLAGS.register_opts(exc_log_opts)


class ConvertedException(webob.exc.WSGIHTTPException):
    def __init__(self, code=0, title="", explanation=""):
        self.code = code
        self.title = title
        self.explanation = explanation
        super(ConvertedException, self).__init__()


class ProcessExecutionError(IOError):
    def __init__(self, stdout=None, stderr=None, exit_code=None, cmd=None,
                 description=None):
        self.exit_code = exit_code
        self.stderr = stderr
        self.stdout = stdout
        self.cmd = cmd
        self.description = description

        if description is None:
            description = _('Unexpected error while running command.')
        if exit_code is None:
            exit_code = '-'
        message = _('%(description)s\nCommand: %(cmd)s\n'
                    'Exit code: %(exit_code)s\nStdout: %(stdout)r\n'
                    'Stderr: %(stderr)r') % locals()
        IOError.__init__(self, message)


class Error(Exception):
    pass


class DBError(Error):
    """Wraps an implementation specific exception."""
    def __init__(self, inner_exception=None):
        self.inner_exception = inner_exception
        super(DBError, self).__init__(str(inner_exception))


def wrap_db_error(f):
    def _wrap(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except UnicodeEncodeError:
            raise InvalidUnicodeParameter()
        except Exception, e:
            LOG.exception(_('DB exception wrapped.'))
            raise DBError(e)
    _wrap.func_name = f.func_name
    return _wrap

def wrap_exception(notifier=None, publisher_id=None, event_type=None,
                   level=None):
    """This decorator wraps a method to catch any exceptions that may
    get thrown. It logs the exception as well as optionally sending
    it to the notification system.
    """
    # TODO(sandy): Find a way to import nova.notifier.api so we don't have
    # to pass it in as a parameter. Otherwise we get a cyclic import of
    # nova.notifier.api -> nova.utils -> nova.exception :(
    def inner(f):
        def wrapped(self, context, *args, **kw):
            # Don't store self or context in the payload, it now seems to
            # contain confidential information.
            try:
                return f(self, context, *args, **kw)
            except Exception, e:
                with excutils.save_and_reraise_exception():
                    if notifier:
                        payload = dict(exception=e)
                        call_dict = safe_utils.getcallargs(f, *args, **kw)
                        cleansed = _cleanse_dict(call_dict)
                        payload.update({'args': cleansed})

                        # Use a temp vars so we don't shadow
                        # our outer definitions.
                        temp_level = level
                        if not temp_level:
                            temp_level = notifier.ERROR

                        temp_type = event_type
                        if not temp_type:
                            # If f has multiple decorators, they must use
                            # functools.wraps to ensure the name is
                            # propagated.
                            temp_type = f.__name__

                        notifier.notify(context, publisher_id, temp_type,
                                        temp_level, payload)

    return inner


class RakshaException(Exception):
    """Base Raksha Exception

    To correctly use this class, inherit from it and define
    a 'message' property. That message will get printf'd
    with the keyword arguments provided to the constructor.

    """
    message = _("An unknown exception occurred.")
    code = 500
    headers = {}
    safe = False

    def __init__(self, message=None, **kwargs):
        self.kwargs = kwargs

        if 'code' not in self.kwargs:
            try:
                self.kwargs['code'] = self.code
            except AttributeError:
                pass

        if not message:
            try:
                message = self.message % kwargs

            except Exception as e:
                # kwargs doesn't match a variable in the message
                # log the issue and the kwargs
                LOG.exception(_('Exception in string format operation'))
                for name, value in kwargs.iteritems():
                    LOG.error("%s: %s" % (name, value))
                if FLAGS.fatal_exception_format_errors:
                    raise e
                else:
                    # at least get the core message out if something happened
                    message = self.message

        super(RakshaException, self).__init__(message)


class GlanceConnectionFailed(RakshaException):
    message = _("Connection to glance failed") + ": %(reason)s"


class NotAuthorized(RakshaException):
    message = _("Not authorized.")
    code = 403


class AdminRequired(NotAuthorized):
    message = _("User does not have admin privileges")


class PolicyNotAuthorized(NotAuthorized):
    message = _("Policy doesn't allow %(action)s to be performed.")


class ImageNotAuthorized(RakshaException):
    message = _("Not authorized for image %(image_id)s.")


class Invalid(RakshaException):
    message = _("Unacceptable parameters.")
    code = 400


class InvalidSnapshot(Invalid):
    message = _("Invalid snapshot") + ": %(reason)s"


class VolumeAttached(Invalid):
    message = _("Volume %(volume_id)s is still attached, detach volume first.")


class SfJsonEncodeFailure(RakshaException):
    message = _("Failed to load data into json format")


class InvalidRequest(Invalid):
    message = _("The request is invalid.")


class InvalidResults(Invalid):
    message = _("The results are invalid.")


class InvalidInput(Invalid):
    message = _("Invalid input received") + ": %(reason)s"


class InvalidVolumeType(Invalid):
    message = _("Invalid volume type") + ": %(reason)s"


class InvalidVolume(Invalid):
    message = _("Invalid volume") + ": %(reason)s"


class InvalidContentType(Invalid):
    message = _("Invalid content type %(content_type)s.")


class InvalidUnicodeParameter(Invalid):
    message = _("Invalid Parameter: "
                "Unicode is not supported by the current database.")


# Cannot be templated as the error syntax varies.
# msg needs to be constructed when raised.
class InvalidParameterValue(Invalid):
    message = _("%(err)s")


class ServiceUnavailable(Invalid):
    message = _("Service is unavailable at this time.")


class ImageUnacceptable(Invalid):
    message = _("Image %(image_id)s is unacceptable: %(reason)s")


class InvalidUUID(Invalid):
    message = _("Expected a uuid but received %(uuid).")


class NotFound(RakshaException):
    message = _("Resource could not be found.")
    code = 404
    safe = True


class PersistentVolumeFileNotFound(NotFound):
    message = _("Volume %(volume_id)s persistence file could not be found.")


class VolumeNotFound(NotFound):
    message = _("Volume %(volume_id)s could not be found.")


class SfAccountNotFound(NotFound):
    message = _("Unable to locate account %(account_name)s on "
                "Solidfire device")


class VolumeNotFoundForInstance(VolumeNotFound):
    message = _("Volume not found for instance %(instance_id)s.")


class VolumeMetadataNotFound(NotFound):
    message = _("Volume %(volume_id)s has no metadata with "
                "key %(metadata_key)s.")


class InvalidVolumeMetadata(Invalid):
    message = _("Invalid metadata") + ": %(reason)s"


class InvalidVolumeMetadataSize(Invalid):
    message = _("Invalid metadata size") + ": %(reason)s"


class SnapshotMetadataNotFound(NotFound):
    message = _("Snapshot %(snapshot_id)s has no metadata with "
                "key %(metadata_key)s.")


class InvalidSnapshotMetadata(Invalid):
    message = _("Invalid metadata") + ": %(reason)s"


class InvalidSnapshotMetadataSize(Invalid):
    message = _("Invalid metadata size") + ": %(reason)s"


class VolumeTypeNotFound(NotFound):
    message = _("Volume type %(volume_type_id)s could not be found.")


class VolumeTypeNotFoundByName(VolumeTypeNotFound):
    message = _("Volume type with name %(volume_type_name)s "
                "could not be found.")


class VolumeTypeExtraSpecsNotFound(NotFound):
    message = _("Volume Type %(volume_type_id)s has no extra specs with "
                "key %(extra_specs_key)s.")


class SnapshotNotFound(NotFound):
    message = _("Snapshot %(snapshot_id)s could not be found.")


class VolumeIsBusy(RakshaException):
    message = _("deleting volume %(volume_name)s that has snapshot")


class SnapshotIsBusy(RakshaException):
    message = _("deleting snapshot %(snapshot_name)s that has "
                "dependent volumes")


class ISCSITargetNotFoundForVolume(NotFound):
    message = _("No target id found for volume %(volume_id)s.")


class ISCSITargetCreateFailed(RakshaException):
    message = _("Failed to create iscsi target for volume %(volume_id)s.")


class ISCSITargetAttachFailed(RakshaException):
    message = _("Failed to attach iSCSI target for volume %(volume_id)s.")


class ISCSITargetRemoveFailed(RakshaException):
    message = _("Failed to remove iscsi target for volume %(volume_id)s.")


class DiskNotFound(NotFound):
    message = _("No disk at %(location)s")


class InvalidImageRef(Invalid):
    message = _("Invalid image href %(image_href)s.")


class ImageNotFound(NotFound):
    message = _("Image %(image_id)s could not be found.")


class ServiceNotFound(NotFound):
    message = _("Service %(service_id)s could not be found.")


class HostNotFound(NotFound):
    message = _("Host %(host)s could not be found.")


class SchedulerHostFilterNotFound(NotFound):
    message = _("Scheduler Host Filter %(filter_name)s could not be found.")


class SchedulerHostWeigherNotFound(NotFound):
    message = _("Scheduler Host Weigher %(weigher_name)s could not be found.")


class HostBinaryNotFound(NotFound):
    message = _("Could not find binary %(binary)s on host %(host)s.")


class InvalidReservationExpiration(Invalid):
    message = _("Invalid reservation expiration %(expire)s.")


class InvalidQuotaValue(Invalid):
    message = _("Change would make usage less than 0 for the following "
                "resources: %(unders)s")


class QuotaNotFound(NotFound):
    message = _("Quota could not be found")


class QuotaResourceUnknown(QuotaNotFound):
    message = _("Unknown quota resources %(unknown)s.")


class ProjectQuotaNotFound(QuotaNotFound):
    message = _("Quota for project %(project_id)s could not be found.")


class QuotaClassNotFound(QuotaNotFound):
    message = _("Quota class %(class_name)s could not be found.")


class QuotaUsageNotFound(QuotaNotFound):
    message = _("Quota usage for project %(project_id)s could not be found.")


class ReservationNotFound(QuotaNotFound):
    message = _("Quota reservation %(uuid)s could not be found.")


class OverQuota(RakshaException):
    message = _("Quota exceeded for resources: %(overs)s")


class MigrationNotFound(NotFound):
    message = _("Migration %(migration_id)s could not be found.")


class MigrationNotFoundByStatus(MigrationNotFound):
    message = _("Migration not found for instance %(instance_id)s "
                "with status %(status)s.")


class FileNotFound(NotFound):
    message = _("File %(file_path)s could not be found.")


class ClassNotFound(NotFound):
    message = _("Class %(class_name)s could not be found: %(exception)s")


class NotAllowed(RakshaException):
    message = _("Action not allowed.")


#TODO(bcwaldon): EOL this exception!
class Duplicate(RakshaException):
    pass


class KeyPairExists(Duplicate):
    message = _("Key pair %(key_name)s already exists.")


class VolumeTypeExists(Duplicate):
    message = _("Volume Type %(id)s already exists.")


class MigrationError(RakshaException):
    message = _("Migration error") + ": %(reason)s"


class MalformedRequestBody(RakshaException):
    message = _("Malformed message body: %(reason)s")


class ConfigNotFound(NotFound):
    message = _("Could not find config at %(path)s")


class PasteAppNotFound(NotFound):
    message = _("Could not load paste app '%(name)s' from %(path)s")


class NoValidHost(RakshaException):
    message = _("No valid host was found. %(reason)s")


class WillNotSchedule(RakshaException):
    message = _("Host %(host)s is not up or doesn't exist.")


class QuotaError(RakshaException):
    message = _("Quota exceeded") + ": code=%(code)s"
    code = 413
    headers = {'Retry-After': 0}
    safe = True


class VolumeSizeExceedsAvailableQuota(QuotaError):
    message = _("Requested volume or snapshot exceeds "
                "allowed Gigabytes quota")


class VolumeSizeExceedsQuota(QuotaError):
    message = _("Maximum volume/snapshot size exceeded")


class VolumeLimitExceeded(QuotaError):
    message = _("Maximum number of volumes allowed (%(allowed)d) exceeded")


class SnapshotLimitExceeded(QuotaError):
    message = _("Maximum number of snapshots allowed (%(allowed)d) exceeded")


class DuplicateSfVolumeNames(Duplicate):
    message = _("Detected more than one volume with name %(vol_name)s")


class Duplicate3PARHost(RakshaException):
    message = _("3PAR Host already exists: %(err)s.  %(info)s")


class Invalid3PARDomain(RakshaException):
    message = _("Invalid 3PAR Domain: %(err)s")


class VolumeTypeCreateFailed(RakshaException):
    message = _("Cannot create volume_type with "
                "name %(name)s and specs %(extra_specs)s")


class SolidFireAPIException(RakshaException):
    message = _("Bad response from SolidFire API")


class SolidFireAPIDataException(SolidFireAPIException):
    message = _("Error in SolidFire API response: data=%(data)s")


class UnknownCmd(Invalid):
    message = _("Unknown or unsupported command %(cmd)s")


class MalformedResponse(Invalid):
    message = _("Malformed response to command %(cmd)s: %(reason)s")


class BadHTTPResponseStatus(RakshaException):
    message = _("Bad HTTP response status %(status)s")


class FailedCmdWithDump(RakshaException):
    message = _("Operation failed with status=%(status)s. Full dump: %(data)s")


class ZadaraServerCreateFailure(RakshaException):
    message = _("Unable to create server object for initiator %(name)s")


class ZadaraServerNotFound(NotFound):
    message = _("Unable to find server object for initiator %(name)s")


class ZadaraVPSANoActiveController(RakshaException):
    message = _("Unable to find any active VPSA controller")


class ZadaraAttachmentsNotFound(NotFound):
    message = _("Failed to retrieve attachments for volume %(name)s")


class ZadaraInvalidAttachmentInfo(Invalid):
    message = _("Invalid attachment info for volume %(name)s: %(reason)s")


class InstanceNotFound(NotFound):
    message = _("Instance %(instance_id)s could not be found.")


class VolumeBackendAPIException(RakshaException):
    message = _("Bad or unexpected response from the storage volume "
                "backend API: %(data)s")


class NfsException(RakshaException):
    message = _("Unknown NFS exception")


class NfsNoSharesMounted(NotFound):
    message = _("No mounted NFS shares found")


class NfsNoSuitableShareFound(NotFound):
    message = _("There is no share which can host %(volume_size)sG")


class GlusterfsException(RakshaException):
    message = _("Unknown Gluster exception")


class GlusterfsNoSharesMounted(NotFound):
    message = _("No mounted Gluster shares found")


class GlusterfsNoSuitableShareFound(NotFound):
    message = _("There is no share which can host %(volume_size)sG")


class GlanceMetadataExists(Invalid):
    message = _("Glance metadata cannot be updated, key %(key)s"
                " exists for volume id %(volume_id)s")


class ImageCopyFailure(Invalid):
    message = _("Failed to copy image to volume")


class BackupJobNotFound(NotFound):
    message = _("BackupJob %(backupjob_id)s could not be found.")

class BackupJobRunNotFound(NotFound):
    message = _("BackupJobRun %(backupjobrun_id)s could not be found.")

class SwiftObjectNotFound(NotFound):
    message = _("SwiftObject %(object_id)s could not be found.")

class InvalidBackupJob(Invalid):
    message = _("Invalid backupjob: %(reason)s")

class SwiftConnectionFailed(RakshaException):
    message = _("Connection to swift failed") + ": %(reason)s"

class VMsofBackupJobNotFound(NotFound):
    message = _("VMs for BackupJob %(backupjob_id)s could not be found.")    
    
class VMsOfBackupJobRunNotFound:
    message = _("VMs for BackupJobRun %(backupjobrun_id)s could not be found.")  

class VMRecentBackupJobRunNotFound:
    message = _("Recent successful BackupJobRun for VM %(vm_id)s could not be found.") 
    
class BackupJobRunVMResourcesNotFound:
    message = _("BackupJobRunVMResources of VM  %(vm_id)s BackupJobRun %(backupjobrun_id)s could not be found.")

class BackupJobRunVMResourcesWithNameNotFound:
    message = _("BackupJobRunVMResource of VM  %(vm_id)s BackupJobRun %(backupjobrun_id)s Resource %(resource_name)s could not be found.")

class BackupJobRunVMResourcesWithIdNotFound:
    message = _("BackupJobRunVMResource with Id  %(id)s could not be found.")
    
class VaultServiceNotFound:
    message = _("Vault Service %(id)s could not be found.")  
    
class VMResourceBackupsNotFound:
    message = _("VM Resource backups for backupjobrun_vm_resource_id %(backupjobrun_vm_resource_id)s could not be found.")  
    