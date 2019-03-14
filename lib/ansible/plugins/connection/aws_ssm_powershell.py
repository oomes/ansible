# Based on the winrm connection plugin by Chris Church
#
# Copyright: (c) 2018, Pat Sharkey <psharkey@cleo.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

DOCUMENTATION = """
author: psharkey@cleo.com
connection: aws_ssm_powershell
short_description: execute via AWS Systems Manager
description:
- This connection plugin allows ansible to execute tasks on an EC2 instance via the aws ssm CLI.
version_added: "2.8"
requirements:
- The control machine must have the aws session manager plugin installed.
options:
  instance_id:
    description: The EC2 instance ID.
    vars:
    - name: instance_id
    - name: aws_instance_id
  region:
    description: The region the EC2 instance is located.
    vars:
    - name: region
    - name: aws_region
    default: 'us-east-1'
  bucket_name:
    description: The name of the S3 bucket used for file transfers.
    vars:
    - name: bucket_name
  plugin:
    description: This defines the location of the session-manager-plugin binary.
    vars:
    - name: session_manager_plugin
    default: '/usr/local/bin/session-manager-plugin'
  retries:
    description: Number of attempts to connect.
    default: 3
    type: integer
    vars:
    - name: ansible_ssm_retries
  timeout:
    description: Connection timeout seconds.
    default: 60
    type: integer
    vars:
    - name: ansible_ssm_timeout
"""

from ansible.plugins.connection.aws_ssm import Connection as AwsSsmConnection


class Connection(AwsSsmConnection):
    ''' AWS SSM based connections for powershell '''

    transport = 'aws_ssm_powershell'
    module_implementation_preferences = ('.ps1', '.exe', '')

    def __init__(self, *args, **kwargs):

        self.protocol = None
        self.shell_id = None
        self.delegate = None
        self._shell_type = 'powershell'

        super(Connection, self).__init__(*args, **kwargs)

    def _prepare_terminal(self):
        ''' perform any one-time terminal settings '''

    def _wrap_command(self, cmd, sudoable, mark_start, mark_end):
        ''' wrap commad so stdout and status can be extracted '''

        return cmd + "; echo $?; echo '" + mark_start + "'\n" + "echo '" + mark_end + "'\n"

    def _file_transport_command(self, in_path, out_path, ssm_action):
        ''' transfer a file from using an intermediate S3 bucket '''

        s3_path = out_path.replace('\\', '/')
        bucket_url = 's3://%s/%s' % (self.get_option('bucket_name'), s3_path)
        get_command = "Invoke-WebRequest '%s' -OutFile '%s'" % (self._get_url('get_object', self.get_option('bucket_name'), s3_path, 'GET'), out_path)

        client = boto3.client('s3')
        if ssm_action == 'get':
            (returncode, stdout, stderr) = self.exec_command(put_command, in_data=None, sudoable=False)
            with open(out_path, 'wb') as data:
                client.download_fileobj(self.get_option('bucket_name'), s3_path, data)
        else:
            with open(in_path, 'rb') as data:
                client.upload_fileobj(data, self.get_option('bucket_name'), s3_path)
            (returncode, stdout, stderr) = self.exec_command(get_command, in_data=None, sudoable=False)

        # Check the return code
        if returncode == 0:
            return (returncode, stdout, stderr)
        else:
            raise AnsibleError("failed to transfer file to %s %s:\n%s\n%s" %
                               (to_native(in_path), to_native(out_path), to_native(stdout), to_native(stderr)))


    def _post_process(self, stdout):
        ''' extract command status and strip unwanted lines '''

        extra_lines = 4
        stdout = stdout.replace('\r', '')
        lines = stdout.splitlines()

        # Get command return code
        if 'True' in lines[-1]:
            extra_lines = 2
            if len(lines) == 1:
                extra_lines = 0
                stdout = ''
            returncode = 0
        elif 'False' in lines[-1]:
            extra_lines = 2
            returncode = -1
        elif 'False' in lines[-2]:
            extra_lines = 2
            returncode = -1
        elif 'True' in lines[-3]:
            returncode = 0
        else:
            returncode = -51

        # Throw away ending lines
        for x in range(0, extra_lines):
            stdout = stdout[:stdout.rfind('\n')]

        return (returncode, stdout)
