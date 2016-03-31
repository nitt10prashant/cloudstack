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

# Import Local Modules
from marvin.cloudstackTestCase import cloudstackTestCase, unittest
from marvin.cloudstackAPI import (updateStoragePool,
                                  resizeVolume,
                                  listCapacity,
                                  addCluster)
from marvin.sshClient import SshClient
from marvin.lib.common import (get_zone,
                               get_template,
                               get_domain,
                               list_volumes,
                               get_pod,
                               is_config_suitable)
from marvin.lib.base import (Domain,
                             Account,
                             Template,
                             VirtualMachine,
                             Volume,
                             DiskOffering,
                             StoragePool,
                             ServiceOffering,
                             Configurations)
from marvin.lib.utils import cleanup_resources
from nose.plugins.attrib import attr
import time


class TestBVTIMPR(cloudstackTestCase):

    @classmethod
    def setUpClass(cls):
        try:
            cls._cleanup = []
            cls.testClient = super(TestBVTIMPR, cls).getClsTestClient()
            cls.apiClient = cls.testClient.getApiClient()
            cls.services = cls.testClient.getParsedTestDataConfig()
            cls.hypervisor = cls.testClient.getHypervisorInfo()
            # Get Domain, Zone, Template
            cls.domain = get_domain(cls.api_client)
            cls.zone = get_zone(cls.api_client,
                                cls.testClient.getZoneForTests())
            cls.pod = get_pod(cls.apiClient, zone_id=cls.zone.id)
            cls.template = get_template(
                cls.apiclient,
                cls.zone.id,
                cls.services["ostype"]
            )
            cls.services['mode'] = cls.zone.networktype
            cls.services["hypervisor"] = cls.testClient.getHypervisorInfo()
            # Creating Disk offering, Service Offering and Account
            cls.service_offering = ServiceOffering.create(
                cls.apiClient,
                cls.services["service_offerings"]["small"]
            )
            cls.account = Account.create(
                cls.apiclient,
                cls.services["account"],
                domainid=cls.domain.id
            )

            cls.vm1_from_template = VirtualMachine.create(
                                     cls.apiclient
            )
            # add objects created in setUpCls to the _cleanup list
            cls._cleanup = [cls.account,
                            cls.service_offering]

        except Exception as e:
            cls.tearDownClass()
            raise Exception("Warning: Exception in setup : %s" % e)
        return

    def setUp(self):

        self.apiClient = self.testClient.getApiClient()
        self.cleanup = []

    def tearDown(self):
        # Clean up, terminate the created resources
        cleanup_resources(self.apiClient, self.cleanup)
        return

    @classmethod
    def tearDownClass(cls):
        try:
            cleanup_resources(cls.api_client, cls._cleanup)
        except Exception as e:
            raise Exception("Warning: Exception during cleanup : %s" % e)

        return

    @attr(tags=["advanced", "basic", "tested"])
    @attr(required_hardware="false")
    def test_01_service_offering(self):
        """
        1-verify service offerings
        """

