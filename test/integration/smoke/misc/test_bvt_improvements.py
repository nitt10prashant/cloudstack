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
from marvin.cloudstackAPI import (changeServiceForVirtualMachine,
                                  updateServiceOffering,
                                  scaleVirtualMachine,
                                  updateDiskOffering,
                                  rebootVirtualMachine)
from marvin.sshClient import SshClient
from marvin.lib.common import (get_zone,
                               get_template,
                               get_domain,
                               list_service_offering,
                               list_volumes,
                               get_pod,
                               is_config_suitable,
                               list_virtual_machines,
                               list_disk_offering)
from marvin.lib.base import (Domain,
                             Account,
                             Template,
                             VirtualMachine,
                             Volume,
                             DiskOffering,
                             StoragePool,
                             ServiceOffering,
                             Configurations,
                             validateList,
                             AffinityGroup,
                             Project,
                             Router,
                             Host)
from marvin.codes import PASS ,FAIL
from marvin.lib.utils import cleanup_resources,random_gen,isAlmostEqual
from nose.plugins.attrib import attr
import time
import re
import string
import random

class TestBVTIMPR(cloudstackTestCase):

    @classmethod
    def setUpClass(cls):
        try:
            cls._cleanup = []
            cls.testClient = super(TestBVTIMPR, cls).getClsTestClient()
            cls.apiclient = cls.testClient.getApiClient()
            cls.dbclient = cls.testClient.getDbConnection()
            cls.services = cls.testClient.getParsedTestDataConfig()
            cls.hypervisor = cls.testClient.getHypervisorInfo()
            # Get Domain, Zone, Template
            cls.domain = get_domain(cls.apiclient)
            cls.zone = get_zone(cls.apiclient,
                                cls.testClient.getZoneForTests())
            cls.pod = get_pod(cls.apiclient, zone_id=cls.zone.id)
            cls.template = get_template(
                cls.apiclient,
                cls.zone.id,
                cls.services["ostype"]
            )
            cls.services['mode'] = cls.zone.networktype
            cls.services["hypervisor"] = cls.testClient.getHypervisorInfo()
            cls.services["small"]["zoneid"] = cls.zone.id
            cls.services["small"]["template"] = cls.template.id

            cls.account = Account.create(
                cls.apiclient,
                cls.services["account"],
                domainid=cls.domain.id
            )


            # Creating Disk offering, Service Offering and Account
            cls.service_offering = ServiceOffering.create(
                cls.apiclient,
                cls.services["service_offerings"]["small"]
            )
            cls.medium_offering = ServiceOffering.create(
                               cls.apiclient,
                               cls.services["service_offerings"]["medium"],
                               isvolatile="true"
                               )

            cls.big_offering = ServiceOffering.create(
                                cls.apiclient,
                               cls.services["service_offerings"]["big"]
                               )


            #create affinity group
            cls.ag = AffinityGroup.create(cls.apiclient, cls.services["virtual_machine"]["affinity"],
            account=cls.account.name, domainid=cls.domain.id)
            cls.services["small"]["userdata"] = cls.services["virtual_machine_userdata"]["userdata"]

            cls.virtual_machine_1 = VirtualMachine.create(
                                  cls.apiclient,
                                  cls.services["small"],
                                  accountid=cls.account.name,
                                  domainid=cls.account.domainid,
                                  serviceofferingid=cls.service_offering.id,
                                  mode=cls.services["mode"],
                                  affinitygroupnames=[cls.ag.name],
                                  method='POST'
                                    )

            cls.virtual_machine_2 = VirtualMachine.create(
                                  cls.apiclient,
                                  cls.services["small"],
                                  templateid=cls.template.id,
                                  accountid=cls.account.name,
                                  domainid=cls.account.domainid,
                                  serviceofferingid=cls.medium_offering.id,
                                  affinitygroupnames=[cls.ag.name]
                                  )


            # add objects created in setUpCls to the _cleanup list
            cls._cleanup = [cls.ag,
                            cls.service_offering,
                            cls.medium_offering,
                            cls.big_offering,
                            cls.account
                            ]

        except Exception as e:
            cls.tearDownClass()
            raise Exception("Warning: Exception in setup : %s" % e)
        return

    def setUp(self):

        self.apiclient = self.testClient.getApiClient()
        self.cleanup = []

    def tearDown(self):
        # Clean up, terminate the created resources
        cleanup_resources(self.apiclient, self.cleanup)

        return

    @classmethod
    def tearDownClass(cls):
        try:
            #test_03_delete_service_offering
            cls.service_offering.delete(cls.apiclient)
            list_service_response = list_service_offering(
                              cls.apiclient,
                              id=cls.service_offering.id
             )
            assert list_service_response == None, "check if service offering exist"

            # test_06_expunge_vm from destroy vm script
            cls.virtual_machine_1.delete(cls.apiclient, expunge=False)
            config = Configurations.list(
                                     cls.apiclient,
                                     name='expunge.delay'
                                     )

            expunge_delay = int(config[0].value)
            time.sleep(expunge_delay * 2)

            #VM should be destroyed unless expunge thread hasn't run
            #Wait for two cycles of the expunge thread
            config = Configurations.list(
                                     cls.apiclient,
                                     name='expunge.interval'
                                     )
            expunge_cycle = int(config[0].value)
            wait_time = expunge_cycle * 4
            while wait_time >= 0:
             list_vm_response = VirtualMachine.list(
                                                cls.apiclient,
                                                id=cls.virtual_machine_1.id
                                                )
             if not list_vm_response:
                 break
             cls.debug("Waiting for VM to expunge")
             time.sleep(expunge_cycle)
             wait_time = wait_time - expunge_cycle

            cls.debug("listVirtualMachines response: %s" % list_vm_response)
            assert list_vm_response == None ,"Check Expunged virtual machine is in listVirtualMachines response"



            cleanup_resources(cls.apiclient, cls._cleanup)
        except Exception as e:
            raise Exception("Warning: Exception during cleanup : %s" % e)

        return

    @attr(tags=["advanced", "basic", "tested"])
    @attr(required_hardware="false")
    def test_01_service_offering(self):
        """
        test_01_create_service_offering in old BVT
        1-verify service offerings
        """
        list_service_response = list_service_offering(
                           self.apiclient,
                           id=self.service_offering.id
                           )
        self.assertEqual(
            isinstance(list_service_response, list),
            True,
            "Check list response returns a valid list"
        )
        self.assertNotEqual(
            len(list_service_response),
            0,
            "Check Service offering is created"
        )
        self.assertEqual(
            list_service_response[0].cpunumber,
            self.services["service_offerings"]["small"]["cpunumber"],
            "Check server id in createServiceOffering"
        )
        self.assertEqual(
            list_service_response[0].cpuspeed,
            self.services["service_offerings"]["small"]["cpuspeed"],
            "Check cpuspeed in createServiceOffering"
        )
        self.assertEqual(
            list_service_response[0].displaytext,
            self.services["service_offerings"]["small"]["displaytext"],
            "Check server displaytext in createServiceOfferings"
        )
        self.assertEqual(
            list_service_response[0].memory,
            self.services["service_offerings"]["small"]["memory"],
            "Check memory in createServiceOffering"
        )
        self.assertEqual(
            list_service_response[0].name,
            self.services["service_offerings"]["small"]["name"],
            "Check name in createServiceOffering"
        )
    def test_02_edit_service_offering(self):
        #test_02_edit_service_offering in old BVT

        random_displaytext = random_gen()
        random_name = random_gen()
        self.debug("Updating service offering with ID: %s" %
                   self.service_offering.id)
        cmd = updateServiceOffering.updateServiceOfferingCmd()
        # Add parameters for API call
        cmd.id = self.service_offering.id
        cmd.displaytext = random_displaytext
        cmd.name = random_name
        self.apiclient.updateServiceOffering(cmd)
        cmd.id = self.service_offering.id
        cmd.displaytext = random_displaytext
        cmd.name = random_name
        self.apiclient.updateServiceOffering(cmd)

        list_service_response = list_service_offering(
            self.apiclient,
            id=self.service_offering.id
        )
        self.assertEqual(
            isinstance(list_service_response, list),
            True,
            "Check list response returns a valid list"
        )

        self.assertNotEqual(
            len(list_service_response),
            0,
            "Check Service offering is updated"
        )

        self.assertEqual(
            list_service_response[0].displaytext,
            random_displaytext,
            "Check server displaytext in updateServiceOffering"
        )
        self.assertEqual(
            list_service_response[0].name,
            random_name,
            "Check server name in updateServiceOffering"
        )
    def test_03_change_offering_small(self):
        #test case change service offering of a vm still need to change so to back to small

        if self.hypervisor.lower() == "lxc":
            self.skipTest("Skipping this test for {} due to bug CS-38153".format(self.hypervisor))
        try:
            self.virtual_machine_1.stop(self.apiclient)
        except Exception as e:
            self.fail("Failed to stop VM: %s" % e)

        cmd = changeServiceForVirtualMachine.changeServiceForVirtualMachineCmd()
        cmd.id = self.virtual_machine_1.id
        cmd.serviceofferingid = self.medium_offering.id
        self.apiclient.changeServiceForVirtualMachine(cmd)

        self.debug("Starting VM - ID: %s" % self.virtual_machine_1.id)
        self.virtual_machine_1.start(self.apiclient)
        # Ensure that VM is in running state
        list_vm_response = list_virtual_machines(
            self.apiclient,
            id=self.virtual_machine_1.id
        )

        if isinstance(list_vm_response, list):
            vm = list_vm_response[0]
            if vm.state == 'Running':
                self.debug("VM state: %s" % vm.state)
            else:
                raise Exception(
                    "Failed to start VM (ID: %s) after changing\
                            service offering" % vm.id)

        try:
            ssh = self.virtual_machine_1.get_ssh_client()
        except Exception as e:
            self.fail(
                "SSH Access failed for %s: %s" %
                (self.virtual_machine_1.ipaddress, e)
            )

        cpuinfo = ssh.execute("cat /proc/cpuinfo")
        cpu_cnt = len([i for i in cpuinfo if "processor" in i])
        # 'cpu MHz\t\t: 2660.499'
        cpu_speed = [i for i in cpuinfo if "cpu MHz" in i][0].split()[3]
        meminfo = ssh.execute("cat /proc/meminfo")
        # MemTotal:        1017464 kB
        total_mem = [i for i in meminfo if "MemTotal" in i][0].split()[1]

        self.debug(
            "CPU count: %s, CPU Speed: %s, Mem Info: %s" % (
                cpu_cnt,
                cpu_speed,
                total_mem
            ))
        self.assertAlmostEqual(
            int(cpu_cnt),
            self.medium_offering.cpunumber,
            "Check CPU Count for small offering"
        )
        self.assertAlmostEqual(
            list_vm_response[0].cpuspeed,
            self.medium_offering.cpuspeed,
            "Check CPU Speed for small offering"
        )

        range = 20
        if self.hypervisor.lower() == "hyperv":
            range = 200
        # TODO: Find the memory allocated to VM on hyperv hypervisor using
        # powershell commands and use that value to equate instead of
        # manipulating range, currently we get the memory count much less
        # because of the UI component
        self.assertTrue(
            isAlmostEqual(int(int(total_mem) / 1024),
                          int(self.medium_offering.memory),
                          range=range
                          ),
            "Check Memory(kb) for small offering"
        )

        try:
            self.virtual_machine_1.stop(self.apiclient)
            cmd = changeServiceForVirtualMachine.changeServiceForVirtualMachineCmd()
            cmd.id = self.virtual_machine_1.id
            cmd.serviceofferingid = self.service_offering.id
            self.apiclient.changeServiceForVirtualMachine(cmd)

            self.debug("Starting VM - ID: %s" % self.virtual_machine_1.id)
            self.virtual_machine_1.start(self.apiclient)
        except Exception as e:
            self.fail("Failed to change so due to : %s" % e)
        return
    #test affinity froup
    @attr(tags=["basic", "advanced", "multihost"], required_hardware="false")
    def test_04_DeployVmAntiAffinityGroup(self):
        """
        test DeployVM in anti-affinity groups

        deploy VM1 and VM2 in the same host-anti-affinity groups
        Verify that the vms are deployed on separate hosts
        """
        #check if vm1  is in affinity group created in setUp
        list_vm1 = list_virtual_machines(
            self.apiclient,
            id=self.virtual_machine_1.id
        )
        self.assertEqual(
            isinstance(list_vm1, list),
            True,
            "Check list response returns a valid list"
        )
        self.assertNotEqual(
            len(list_vm1),
            0,
            "Check VM available in List Virtual Machines"
        )
        vm1_response = list_vm1[0]
        self.assertEqual(
            vm1_response.state,
            'Running',
            msg="VM is not in Running state"
        )
        host_of_vm1 = vm1_response.hostid

        #check if vm2  is in affinity group created in setUp
        list_vm2 = list_virtual_machines(
            self.apiclient,
            id=self.virtual_machine_2.id
        )
        self.assertEqual(
            isinstance(list_vm2, list),
            True,
            "Check list response returns a valid list"
        )
        self.assertNotEqual(
            len(list_vm2),
            0,
            "Check VM available in List Virtual Machines"
        )
        vm2_response = list_vm2[0]
        self.assertEqual(
            vm2_response.state,
            'Running',
            msg="VM is not in Running state"
        )
        host_of_vm2 = vm2_response.hostid

        self.assertNotEqual(host_of_vm1, host_of_vm2,
            msg="Both VMs of affinity group %s are on the same host" % self.ag.name)

    #test deploy vertual machine test cases
    @attr(tags = ["devcloud", "advanced", "advancedns", "smoke", "basic", "sg"], required_hardware="false")
    def test_05_deploy_vm(self):
        """Test Deploy Virtual Machine
        """
        # Validate the following:
        # 1. Virtual Machine is accessible via SSH
        # 2. listVirtualMachines returns accurate information
        list_vm_response = VirtualMachine.list(
                                                 self.apiclient,
                                                 id=self.virtual_machine_1.id
                                                 )

        self.debug(
                "Verify listVirtualMachines response for virtual machine: %s" \
                % self.virtual_machine_1.id
            )
        self.assertEqual(
                            isinstance(list_vm_response, list),
                            True,
                            "Check list response returns a valid list"
                        )
        self.assertNotEqual(
                            len(list_vm_response),
                            0,
                            "Check VM available in List Virtual Machines"
                        )
        vm_response = list_vm_response[0]
        self.assertEqual(

                            vm_response.id,
                            self.virtual_machine_1.id,
                            "Check virtual machine id in listVirtualMachines"
                        )
        self.assertEqual(
                    vm_response.name,
                    self.virtual_machine_1.name,
                    "Check virtual machine name in listVirtualMachines"
                    )
        self.assertEqual(
            vm_response.state,
            'Running',
             msg="VM is not in Running state"
        )
        list_vm_response_2 = VirtualMachine.list(
                                                 self.apiclient,
                                                 id=self.virtual_machine_2.id
                                                 )

        self.debug(
                "Verify listVirtualMachines response for virtual machine: %s" \
                % self.virtual_machine_2.id
            )
        self.assertEqual(
                            isinstance(list_vm_response_2, list),
                            True,
                            "Check list response returns a valid list"
                        )
        self.assertNotEqual(
                            len(list_vm_response_2),
                            0,
                            "Check VM available in List Virtual Machines"
                        )
        vm_response_2 = list_vm_response_2[0]
        self.assertEqual(

                            vm_response_2.id,
                            self.virtual_machine_2.id,
                            "Check virtual machine id in listVirtualMachines"
                        )
        self.assertEqual(
                    vm_response_2.name,
                    self.virtual_machine_2.name,
                    "Check virtual machine name in listVirtualMachines"
                    )
        self.assertEqual(
            vm_response_2.state,
            'Running',
             msg="VM is not in Running state"
        )
        return

    @attr(tags = ['advanced','basic','sg'], required_hardware="false")
    def test_06_deploy_vm_multiple(self):
        """Test Multiple Deploy Virtual Machine

        # Validate the following:
        # 1. deploy 2 virtual machines
        # 2. listVirtualMachines using 'ids' parameter returns accurate information
        """
        list_vms = VirtualMachine.list(self.apiclient, ids=[self.virtual_machine_1.id, self.virtual_machine_2.id], listAll=True)
        self.debug(
            "Verify listVirtualMachines response for virtual machines: %s, %s" % (self.virtual_machine_1.id, self.virtual_machine_2.id)
        )
        self.assertEqual(
            isinstance(list_vms, list),
            True,
            "List VM response was not a valid list"
        )
        self.assertEqual(
            len(list_vms),
            2,
            "List VM response was empty, expected 2 VMs"
        )
    @attr(tags = ["advanced","basic"], required_hardware="false")
    def test_07_advZoneVirtualRouter(self):
        """
        Test advanced zone virtual router
        1. Is Running
        2. is in the account the VM was deployed in
        3. Has a linklocalip, publicip and a guestip
        @return:
        """
        routers = Router.list(self.apiclient, account=self.account.name)
        self.assertTrue(len(routers) > 0, msg = "No virtual router found")
        router = routers[0]

        self.assertEqual(router.state, 'Running', msg="Router is not in running state")
        self.assertEqual(router.account, self.account.name, msg="Router does not belong to the account")
        self.assertIsNotNone(router.guestipaddress, msg="Router has no guest ip")
        self.assertIsNotNone(router.linklocalip, msg="Router has no linklocal ip")
        if self.services['mode'] == "Advanced":
                       #Has linklocal, public and guest ips
                       self.assertIsNotNone(router.publicip, msg="Router has no public ip")


    @attr(tags = ["devcloud", "advanced", "advancedns", "smoke", "basic", "sg"], required_hardware="false")
    def test_08_stop_start_vm(self):
        """Test Stop Virtual Machine
        """

        # Validate the following
        # 1. Should Not be able to login to the VM.
        # 2. listVM command should return
        #    this VM.State of this VM should be ""Stopped"".
        try:
            self.virtual_machine_1 .stop(self.apiclient)
            self.debug("Starting VM - ID: %s" % self.virtual_machine_1.id)
            self.virtual_machine_1.start(self.apiclient)
            list_vm_response = VirtualMachine.list(
                                            self.apiclient,
                                            id=self.virtual_machine_1.id
                                            )
            self.assertEqual(
                            isinstance(list_vm_response, list),
                            True,
                            "Check list response returns a valid list"
                        )

            self.assertNotEqual(
                            len(list_vm_response),
                            0,
                            "Check VM avaliable in List Virtual Machines"
                        )

            self.debug(
                "Verify listVirtualMachines response for virtual machine: %s" \
                % self.virtual_machine_1.id
                )
            self.assertEqual(
                            list_vm_response[0].state,
                            "Running",
                            "Check virtual machine is in running state"
                        )
        except Exception as e:
            self.fail("Failed to stop/start VM: %s" % e)

        return

    @attr(tags = ["devcloud", "advanced", "advancedns", "smoke", "basic", "sg"], required_hardware="false")
    def test_09_reboot_vm(self):
        """Test Reboot Virtual Machine which is deployed using isvolatile="true" service offerings
        """

        # Validate the following
        # 1. Should be able to login to the VM.
        # 2. listVM command should return the deployed VM.
        #    State of this VM should be "Running"

        volumelist_before_reboot = Volume.list(
            self.apiclient,
            virtualmachineid=self.virtual_machine_2.id,
            type='ROOT',
            listall=True
        )
        self.assertNotEqual(
            volumelist_before_reboot,
            None,
            "Check if volume is in listvolumes"
        )
        volume_before_reboot = volumelist_before_reboot[0]
        self.debug("Rebooting VM - ID: %s" % self.virtual_machine_2.id)
        self.virtual_machine_2.reboot(self.apiclient)

        list_vm_response = VirtualMachine.list(
                                            self.apiclient,
                                            id=self.virtual_machine_2.id
                                            )
        self.assertEqual(
                            isinstance(list_vm_response, list),
                            True,
                            "Check list response returns a valid list"
                        )

        self.assertNotEqual(
                            len(list_vm_response),
                            0,
                            "Check VM avaliable in List Virtual Machines"
                        )

        self.assertEqual(
                            list_vm_response[0].state,
                            "Running",
                            "Check virtual machine is in running state"
                        )

        volumelist_after_reboot = Volume.list(
            self.apiclient,
            virtualmachineid=self.virtual_machine_2.id,
            type='ROOT',
            listall=True
        )

        self.assertNotEqual(
            volumelist_after_reboot,
            None,
            "Check if volume is in listvolumes"
        )

        volume_after_reboot = volumelist_after_reboot[0]
        self.assertNotEqual(
            volume_after_reboot.id,
            volume_before_reboot.id,
            "Check whether volumes are different before and after reboot"
        )

        return

    @attr(tags = ["devcloud", "advanced", "advancedns", "smoke", "basic", "sg"], required_hardware="false")
    def test_10_destroy_recover_vm(self):
        # Validate the following
        # 1. Should not be able to login to the VM.
        # 2. listVM command should return this VM.State
        #    of this VM should be "Destroyed".

        self.debug("Destroy VM - ID: %s" % self.virtual_machine_1.id)
        self.virtual_machine_1.delete(self.apiclient, expunge=False)

        list_vm_response = VirtualMachine.list(
                                            self.apiclient,
                                            id=self.virtual_machine_1.id
                                            )
        self.assertEqual(
                            isinstance(list_vm_response, list),
                            True,
                            "Check list response returns a valid list"
                        )

        self.assertNotEqual(
                            len(list_vm_response),
                            0,
                            "Check VM avaliable in List Virtual Machines"
                        )

        self.assertEqual(
                            list_vm_response[0].state,
                            "Destroyed",
                            "Check virtual machine is in destroyed state"
                        )
        #TODO: SIMENH: add another test the data on the restored VM.
        """Test recover Virtual Machine
        """

        # Validate the following
        # 1. listVM command should return this VM.
        #    State of this VM should be "Stopped".
        # 2. We should be able to Start this VM successfully.

        self.debug("Recovering VM - ID: %s" % self.virtual_machine_1.id)

        self.virtual_machine_1.recover(self.apiclient)
        """
        cmd = recoverVirtualMachine.recoverVirtualMachineCmd()
        cmd.id = self.small_virtual_machine.id
        self.apiclient.recoverVirtualMachine(cmd)
        """
        list_vm_response = VirtualMachine.list(
                                            self.apiclient,
                                            id=self.virtual_machine_1.id
                                            )
        self.assertEqual(
                            isinstance(list_vm_response, list),
                            True,
                            "Check list response returns a valid list"
                        )

        self.assertNotEqual(
                            len(list_vm_response),
                            0,
                            "Check VM avaliable in List Virtual Machines"
                        )

        self.assertEqual(
                            list_vm_response[0].state,
                            "Stopped",
                            "Check virtual machine is in Stopped state"
                        )

        #bring the vm to running state ,required in other test cases
        try:
         self.virtual_machine_1.start(self.apiclient)
        except Exception as e:
            raise Exception("Warning: Exception during start vm : %s" % e)

        return

    @attr(tags = ["advanced", "advancedns", "smoke", "basic", "sg", "multihost"], required_hardware="false")
    def test_11_migrate_vm(self):
        """Test migrate VM
        """
        # Validate the following
        # 1. Environment has enough hosts for migration
        # 2. DeployVM on suitable host (with another host in the cluster)
        # 3. Migrate the VM and assert migration successful

        suitable_hosts = None

        hosts = Host.list(
            self.apiclient,
            zoneid=self.zone.id,
            type='Routing'
        )
        self.assertEqual(validateList(hosts)[0], PASS, "hosts list validation failed")

        if len(hosts) < 2:
            self.skipTest("At least two hosts should be present in the zone for migration")

        if self.hypervisor.lower() in ["lxc"]:
            self.skipTest("Migration is not supported on LXC")

        # For KVM, two hosts used for migration should  be present in same cluster
        # For XenServer and VMware, migration is possible between hosts belonging to different clusters
        # with the help of XenMotion and Vmotion respectively.

        if self.hypervisor.lower() in ["kvm","simulator"]:
            #identify suitable host
            clusters = [h.clusterid for h in hosts]
            #find hosts withe same clusterid
            clusters = [cluster for index, cluster in enumerate(clusters) if clusters.count(cluster) > 1]

            if len(clusters) <= 1:
                self.skipTest("In " + self.hypervisor.lower() + " Live Migration needs two hosts within same cluster")

            suitable_hosts = [host for host in hosts if host.clusterid == clusters[0]]
        else:
            suitable_hosts = hosts

        target_host = suitable_hosts[0]
        migrate_host = suitable_hosts[1]

        #deploy VM on target host
        self.vm_to_migrate = VirtualMachine.create(
            self.apiclient,
            self.services["small"],
            accountid=self.account.name,
            domainid=self.account.domainid,
            serviceofferingid=self.service_offering.id,
            mode=self.services["mode"],
            hostid=target_host.id
        )
        self.debug("Migrating VM-ID: %s to Host: %s" % (
                                        self.vm_to_migrate.id,
                                        migrate_host.id
                                        ))

        self.vm_to_migrate.migrate(self.apiclient, migrate_host.id)

        retries_cnt = 3
        while retries_cnt >=0:
            list_vm_response = VirtualMachine.list(self.apiclient,
                                                   id=self.vm_to_migrate.id)
            self.assertNotEqual(
                                list_vm_response,
                                None,
                                "Check virtual machine is listed"
                               )
            vm_response = list_vm_response[0]
            self.assertEqual(vm_response.id,self.vm_to_migrate.id,"Check virtual machine ID of migrated VM")
            self.assertEqual(vm_response.hostid,migrate_host.id,"Check destination hostID of migrated VM")
            retries_cnt = retries_cnt - 1
        return
    #deploy vm with root resize
    @attr(tags = ['advanced', 'basic', 'sg'], required_hardware="true")
    def test_12_deploy_vm_root_resize(self):
        """Test proper failure to deploy virtual machine with rootdisksize less than template size
        """
        if (self.hypervisor.lower() == 'kvm'):
            newrootsize = (self.template.size >> 30) - 1

            self.assertEqual(newrootsize > 0, True, "Provided template is less than 1G in size, cannot run test")

            success = False
            try:
                self.virtual_machine = VirtualMachine.create(
                    self.apiclient,
                    self.services["small"],
                    accountid=self.account.name,
                    zoneid=self.zone.id,
                    domainid=self.account.domainid,
                    serviceofferingid=self.service_offering.id,
                    templateid=self.template.id,
                    rootdisksize=newrootsize
                )
            except Exception as ex:
                if "rootdisksize override is smaller than template size" in str(ex):
                    success = True
                else:
                    self.debug("virtual machine create did not fail appropriately. Error was actually : " + str(ex));

            self.assertEqual(success, True, "Check if passing rootdisksize < templatesize fails appropriately")
        else:
            self.debug("test test_12_deploy_vm_root_resize does not support hypervisor type " + self.hypervisor);
    @attr(tags = ['advanced', 'basic', 'sg'], required_hardware="true")
    def test_13_deploy_vm_root_resize(self):
        """Test proper failure to deploy virtual machine with rootdisksize of 0
        """
        if (self.hypervisor.lower() == 'kvm'):
            newrootsize = 0
            success = False
            try:
                self.virtual_machine = VirtualMachine.create(
                    self.apiclient,
                    self.services["small"],
                    accountid=self.account.name,
                    zoneid=self.zone.id,
                    domainid=self.account.domainid,
                    serviceofferingid=self.service_offering.id,
                    templateid=self.template.id,
                    rootdisksize=newrootsize
                )
            except Exception as ex:
                if "rootdisk size should be a non zero number" in str(ex):
                    success = True
                else:
                    self.debug("virtual machine create did not fail appropriately. Error was actually : " + str(ex));

            self.assertEqual(success, True, "Check if passing 0 as rootdisksize fails appropriately")
        else:
            self.debug("test 01 does not support hypervisor type " + self.hypervisor);
    @attr(tags = ['advanced', 'basic', 'sg'], required_hardware="true")
    def test_14_deploy_vm_root_resize(self):
        """Test deploy virtual machine with root resize

        # Validate the following:
        # 1. listVirtualMachines returns accurate information
        # 2. root disk has new size per listVolumes
        # 3. Rejects non-supported hypervisor types
        """
        if(self.hypervisor.lower() == 'kvm'):
            newrootsize = (self.template.size >> 30) + 2
            self.virtual_machine = VirtualMachine.create(
                self.apiclient,
                self.services["small"],
                accountid=self.account.name,
                zoneid=self.zone.id,
                domainid=self.account.domainid,
                serviceofferingid=self.service_offering.id,
                templateid=self.template.id,
                rootdisksize=newrootsize
            )

            list_vms = VirtualMachine.list(self.apiclient, id=self.virtual_machine.id)

            self.debug(
                "Verify listVirtualMachines response for virtual machine: %s"\
                % self.virtual_machine.id
            )

            self.assertEqual(
                isinstance(list_vms, list),
                True,
                "List VM response was not a valid list"
            )
            self.assertNotEqual(
                len(list_vms),
                0,
                "List VM response was empty"
            )

            vm = list_vms[0]
            self.assertEqual(
                vm.id,
                self.virtual_machine.id,
                "Virtual Machine ids do not match"
            )
            self.assertEqual(
                vm.name,
                self.virtual_machine.name,
                "Virtual Machine names do not match"
            )
            self.assertEqual(
                vm.state,
                "Running",
                msg="VM is not in Running state"
            )

            # get root vol from created vm, verify it is correct size
            list_volume_response = list_volumes(
                                                self.apiclient,
                                                virtualmachineid=self.virtual_machine.id,
                                                type='ROOT',
                                                listall=True
                                                )

            rootvolume = list_volume_response[0]
            success = False
            if rootvolume is not None and rootvolume.size  == (newrootsize << 30):
                success = True

            self.assertEqual(
                             success,
                             True,
                             "Check if the root volume resized appropriately"
                            )
        else:
            self.debug("hypervisor %s unsupported for test 14, verifying it errors properly" % self.hypervisor)

            newrootsize = (self.template.size >> 30) + 2
            success = False
            try:
                self.virtual_machine = VirtualMachine.create(
                    self.apiclient,
                    self.testdata["virtual_machine"],
                    accountid=self.account.name,
                    zoneid=self.zone.id,
                    domainid=self.account.domainid,
                    serviceofferingid=self.service_offering.id,
                    templateid=self.template.id,
                    rootdisksize=newrootsize
                )
            except Exception as ex:
                if re.search("Hypervisor \S+ does not support rootdisksize override", str(ex)):
                    success = True
                else:
                    self.debug("virtual machine create did not fail appropriately. Error was actually : " + str(ex));

            self.assertEqual(success, True, "Check if unsupported hypervisor %s fails appropriately" % self.hypervisor)
    @attr(hypervisor="xenserver")
    @attr(tags=["advanced", "basic"], required_hardware="false")
    def test_15_scale_vm(self):
        """Test scale virtual machine
        """
        # Validate the following
        # Scale up the vm and see if it scales to the new svc offering and is
        # finally in running state

        #        VirtualMachine should be updated to tell cloudstack
        #        it has PV tools
        #        available and successfully scaled. We will only mock
        #        that behaviour
        #        here but it is not expected in production since the VM
        #        scaling is not
        #        guaranteed until tools are installed, vm rebooted

        # If hypervisor is Vmware, then check if
        # the vmware tools are installed and the process is running
        # Vmware tools are necessary for scale VM operation
        if self.hypervisor.lower() == "vmware":
            sshClient = self.virtual_machine_2.get_ssh_client()
            result = str(
                sshClient.execute("service vmware-tools status")).lower()
            self.debug("and result is: %s" % result)
            if not "running" in result:
                self.skipTest("Skipping scale VM operation because\
                    VMware tools are not installed on the VM")

        self.virtual_machine_2.update(
            self.apiclient,
            isdynamicallyscalable='true')

        self.debug("Scaling VM-ID: %s to service offering: %s and state %s" % (
            self.virtual_machine_2.id,
            self.big_offering.id,
            self.virtual_machine_2.state
        ))

        cmd = scaleVirtualMachine.scaleVirtualMachineCmd()
        cmd.serviceofferingid = self.big_offering.id
        cmd.id = self.virtual_machine_2.id
        self.apiclient.scaleVirtualMachine(cmd)

        list_vm_response = VirtualMachine.list(
            self.apiclient,
            id=self.virtual_machine_2.id
        )
        self.assertEqual(
            isinstance(list_vm_response, list),
            True,
            "Check list response returns a valid list"
        )

        self.assertNotEqual(
            list_vm_response,
            None,
            "Check virtual machine is in listVirtualMachines"
        )

        vm_response = list_vm_response[0]
        self.assertEqual(
            vm_response.id,
            self.virtual_machine_2.id,
            "Check virtual machine ID of scaled VM"
        )

        self.debug(
            "Scaling VM-ID: %s from service offering: %s to new service\
                    offering %s and the response says %s" %
            (self.virtual_machine_2.id,
             self.virtual_machine_2.serviceofferingid,
             self.big_offering.id,
             vm_response.serviceofferingid))
        self.assertEqual(
            vm_response.serviceofferingid,
            self.big_offering.id,
            "Check service offering of the VM"
        )

        self.assertEqual(
            vm_response.state,
            'Running',
            "Check the state of VM"
        )
        return

    @attr(tags=["advanced", "basic", "eip", "sg", "advancedns", "smoke"], required_hardware="false")
    def test_16_create_update_delete_disk_offering(self):
        """Test to create disk offering

        # Validate the following:
        # 1. createDiskOfferings should return valid info for new offering
        # 2. The Cloud Database contains the valid information
        """
        disk_offering = DiskOffering.create(
                                        self.apiclient,
                                        self.services["disk_offering"]
                                        )
        self.cleanup.append(disk_offering)

        self.debug("Created Disk offering with ID: %s" % disk_offering.id)

        list_disk_response = list_disk_offering(
                                                self.apiclient,
                                                id=disk_offering.id
                                                )
        self.assertEqual(
                            isinstance(list_disk_response, list),
                            True,
                            "Check list response returns a valid list"
                        )
        self.assertNotEqual(
                            len(list_disk_response),
                            0,
                            "Check Disk offering is created"
                        )
        disk_response = list_disk_response[0]

        self.assertEqual(
                            disk_response.displaytext,
                            self.services["disk_offering"]["displaytext"],
                            "Check server id in createServiceOffering"
                        )
        self.assertEqual(
                            disk_response.name,
                            self.services["disk_offering"]["name"],
                            "Check name in createServiceOffering"
                        )
        ###################################update disk offerings#################
        random_displaytext = random_gen()
        random_name = random_gen()

        self.debug("Updating Disk offering with ID: %s" %
                                    disk_offering.id)

        cmd = updateDiskOffering.updateDiskOfferingCmd()
        cmd.id = disk_offering.id
        cmd.displaytext = random_displaytext
        cmd.name = random_name

        self.apiclient.updateDiskOffering(cmd)

        list_disk_response = list_disk_offering(
                                                self.apiclient,
                                                id=disk_offering.id
                                                )
        self.assertEqual(
                            isinstance(list_disk_response, list),
                            True,
                            "Check list response returns a valid list"
                        )
        self.assertNotEqual(
                            len(list_disk_response),
                            0,
                            "Check disk offering is updated"
                        )

        disk_response = list_disk_response[0]

        self.assertEqual(
                        disk_response.displaytext,
                        random_displaytext,
                        "Check service displaytext in updateServiceOffering"
                        )
        self.assertEqual(
                        disk_response.name,
                        random_name,
                        "Check service name in updateServiceOffering"
                        )
        ###################################delete disk offering################################
        disk_offering.delete(self.apiclient)
        list_disk_response = list_disk_offering(
                                                self.apiclient,
                                                id=disk_offering.id
                                                )

        self.assertEqual(
                        list_disk_response,
                        None,
                        "Check if disk offering exists in listDiskOfferings"
                        )
        return

    @attr(hypervisor="kvm")
    @attr(tags = ["advanced", "basic", "eip", "sg", "advancedns", "simulator", "smoke"])
    def test_17_create_delete_sparse_type_disk_offering(self):
        """Test to create  a sparse type disk offering"""

        # Validate the following:
        # 1. createDiskOfferings should return valid info for new offering
        # 2. The Cloud Database contains the valid information

        disk_offering = DiskOffering.create(
                                        self.apiclient,
                                        self.services["sparse"]
                                        )
        self.cleanup.append(disk_offering)

        self.debug("Created Disk offering with ID: %s" % disk_offering.id)

        list_disk_response = list_disk_offering(
                                                self.apiclient,
                                                id=disk_offering.id
                                                )
        self.assertEqual(
                            isinstance(list_disk_response, list),
                            True,
                            "Check list response returns a valid list"
                        )
        self.assertNotEqual(
                            len(list_disk_response),
                            0,
                            "Check Disk offering is created"
                        )
        disk_response = list_disk_response[0]

        self.assertEqual(
                            disk_response.provisioningtype,
                            self.services["sparse"]["provisioningtype"],
                            "Check provisionig type in createServiceOffering"
                        )
        disk_offering.delete(self.apiclient)
        list_disk_response = list_disk_offering(
                                                self.apiclient,
                                                id=disk_offering.id
                                                )

        self.assertEqual(
                        list_disk_response,
                        None,
                        "Check if disk offering exists in listDiskOfferings"
                        )
        return


    @attr(hypervisor="kvm")
    @attr(tags = ["advanced", "basic", "eip", "sg", "advancedns", "simulator", "smoke"])
    def test_18_create_delete_fat_type_disk_offering(self):
        """Test to create  a sparse type disk offering"""

        # Validate the following:
        # 1. createDiskOfferings should return valid info for new offering
        # 2. The Cloud Database contains the valid information

        disk_offering = DiskOffering.create(
                                        self.apiclient,
                                        self.services["fat"]
                                        )
        self.cleanup.append(disk_offering)

        self.debug("Created Disk offering with ID: %s" % disk_offering.id)

        list_disk_response = list_disk_offering(
                                                self.apiclient,
                                                id=disk_offering.id
                                                )
        self.assertEqual(
                            isinstance(list_disk_response, list),
                            True,
                            "Check list response returns a valid list"
                        )
        self.assertNotEqual(
                            len(list_disk_response),
                            0,
                            "Check Disk offering is created"
                        )
        disk_response = list_disk_response[0]

        self.assertEqual(
                            disk_response.provisioningtype,
                            self.services["fat"]["provisioningtype"],
                            "Check provisionig type in createServiceOffering"
                        )
        disk_offering.delete(self.apiclient)
        list_disk_response = list_disk_offering(
                                                self.apiclient,
                                                id=disk_offering.id
                                                )

        self.assertEqual(
                        list_disk_response,
                        None,
                        "Check if disk offering exists in listDiskOfferings"
                        )

    @attr(tags=["advanced, basic"], required_hardware="true")
    def test_19_positive_tests_usage(self):
        """ Check events in usage_events table when VM creation fails

        Steps:
        1. Create service offering with large resource numbers
        2. Try to deploy a VM
        3. VM creation should fail and VM should be in error state
        4. Destroy the VM with expunge parameter True
        5. Check the events for the account in usage_events table
        6. There should be VM.CREATE, VM.DESTROY, VOLUME.CREATE and
            VOLUME.DELETE events present in the table
        """
        self.services["service_offering"]["cpunumber"] = "8"
        self.services["service_offering"]["cpuspeed"] = "8096"
        self.services["service_offering"]["memory"] = "8096"
        self.service_offering = ServiceOffering.create(
                self.apiclient,
                self.services["service_offering"]
            )
        self.services["small"]["name"]= "badvm"
        # Create VM in account
        with self.assertRaises(Exception):
            VirtualMachine.create(
                self.apiclient,
                self.services["small"],
                templateid=self.template.id,
                accountid=self.account.name,
                domainid=self.account.domainid,
                serviceofferingid=self.service_offering.id,
                zoneid=self.zone.id
            )

        vms = VirtualMachine.list(self.apiclient,
                                  account=self.account.name,
                                  domaind=self.account.domainid,
                                  name="badvm")

        self.assertEqual(validateList(vms)[0], PASS,
                         "Vm list validation failed")

        self.assertEqual(vms[0].state.lower(), "error",
                         "VM should be in error state")

        qresultset = self.dbclient.execute(
            "select id from account where uuid = '%s';"
            % self.account.id
        )
        self.assertEqual(
            isinstance(qresultset, list),
            True,
            "Check DB query result set for valid data"
        )

        self.assertNotEqual(
            len(qresultset),
            0,
            "Check DB Query result set"
        )
        qresult = qresultset[0]

        account_id = qresult[0]
        self.debug("select type from usage_event where account_id = '%s';"
                   % account_id)

        qresultset = self.dbclient.execute(
            "select type from usage_event where account_id = '%s'and resource_name = '%s';"
            % (account_id, vms[0].name)
        )
        self.assertEqual(
            isinstance(qresultset, list),
            True,
            "Check DB query result set for valid data"
        )

        self.assertNotEqual(
            len(qresultset),
            0,
            "Check DB Query result set"
        )
        qresult = str(qresultset)
        self.debug("Query result: %s" % qresult)

        # Check if VM.CREATE, VM.DESTROY events present in usage_event table
        self.assertEqual(
            qresult.count('VM.CREATE'),
            1,
            "Check VM.CREATE event in events table"
        )

        self.assertEqual(
            qresult.count('VM.DESTROY'),
            1,
            "Check VM.DESTROY in list events"
        )

        # Check if VOLUME.CREATE, VOLUME.DELETE events present in usage_event
        # table
        qresultset_vm_id = self.dbclient.execute(
            "select id from vm_instance where uuid = '%s';"
            % vms[0].id
        )
        qresultset_vol = self.dbclient.execute(
            "select name from volumes where instance_id = '%s';"
            % qresultset_vm_id[0][0]
        )

        qresult = self.dbclient.execute(
            "select type from usage_event where account_id = '%s'and resource_name = '%s';"
            % (account_id, qresultset_vol[0][0])
        )


        self.assertEqual(
            qresult[0].count('VOLUME.CREATE'),
            1,
            "Check VOLUME.CREATE in events table"
        )

        self.assertEqual(
            qresult[1].count('VOLUME.DELETE'),
            1,
            "Check VM.DELETE in events table"
        )
        self.service_offering.delete(self.apiclient)
        return