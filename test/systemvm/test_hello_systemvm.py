# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

"""Example of using paramiko and envassert for systemvm tests."""

from nose.plugins.attrib import attr
from envassert import file, package, user
from cuisine import file_write
try:
    from . import SystemVMTestCase
except (ImportError, ValueError):
    from systemvm import SystemVMTestCase


class HelloSystemVMTestCase(SystemVMTestCase):
    @attr(tags=["systemvm"], required_hardware="true")
    def test_hello_systemvm_paramiko(self):
        """Test we can connect to the systemvm over ssh, low-level with paramiko"""
        stdin, stdout, stderr = self.sshClient.exec_command('echo hello')
        result = stdout.read().strip()
        self.assertEqual('hello', result)

    @attr(tags=["systemvm"], required_hardware="true")
    def test_hello_systemvm_envassert(self):
        """Test we can run envassert assertions on the systemvm"""
        assert file.exists('/etc/hosts')

        for packageName in ['dnsmasq', 'haproxy', 'keepalived', 'curl']:
            assert package.installed(packageName)

        assert user.exists('cloud')

    @attr(tags=["systemvm"], required_hardware="true")
    def test_hello_systemvm_cuisine(self):
        """Test we can run cuisine on the systemvm"""
        file_write('/tmp/run_cuisine', 'success!\n')
        assert file.has_line('/tmp/run_cuisine', 'success!')