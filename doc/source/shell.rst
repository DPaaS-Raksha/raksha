The :program:`raksha` shell utility
=========================================

.. program:: raksha
.. highlight:: bash

The :program:`raksha` shell utility interacts with the OpenStack Raksha API
from the command line. It supports the entirety of the OpenStack Raksha API.

You'll need to provide :program:`raksha` with your OpenStack username and
API key. You can do this with the :option:`--os-username`, :option:`--os-password`
and :option:`--os-tenant-name` options, but it's easier to just set them as
environment variables by setting two environment variables:

.. envvar:: OS_USERNAME or RAKSHA_USERNAME

    Your OpenStack Raksha username.

.. envvar:: OS_PASSWORD or RAKSHA_PASSWORD

    Your password.

.. envvar:: OS_TENANT_NAME or RAKSHA_PROJECT_ID

    Project for work.

.. envvar:: OS_AUTH_URL or RAKSHA_URL

    The OpenStack API server URL.

.. envvar:: OS_DPAAS_API_VERSION

    The OpenStack DPAAS API version.

For example, in Bash you'd use::

    export OS_USERNAME=yourname
    export OS_PASSWORD=yadayadayada
    export OS_TENANT_NAME=myproject
    export OS_AUTH_URL=http://...
    export OS_VOLUME_API_VERSION=1

From there, all shell commands take the form::

    raksha <command> [arguments...]

Run :program:`raksha help` to get a full list of all possible commands,
and run :program:`raksha help <command>` to get detailed help for that
command.
