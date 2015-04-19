#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# (c) 2014, René Moser <mail@renemoser.net>
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible. If not, see <http://www.gnu.org/licenses/>.

DOCUMENTATION = '''
---
module: cs_virtualmachine
short_description: Manages virtual machines on Apache CloudStack based clouds.
description:
    - Create, start, restart, stop and destroy on Apache CloudStack, Citrix CloudPlatform and Exoscale.
    - Existing virtual machines will be scaled if service offering is different by stopping and starting the virtual machine.
version_added: '2.0'
author: René Moser
options:
  name:
    description:
      - Name of the virtual machine. Name can only contain ASCII letters. Either C(name) or C(display_name) is required.
    required: false
    default: null
  display_name:
    description:
      - Custom display name of the virtual machine. Either C(name) or C(display_name) is required.
    required: false
    default: null
  group:
    description:
      - Group in where the new virtual machine should be in.
    required: false
    default: null
  state:
    description:
      - State of the virtual machine.
    required: false
    default: 'present'
    choices: [ 'created', 'started', 'running', 'booted', 'stopped', 'halted', 'restarted', 'rebooted', 'present', 'absent', 'destroyed', 'expunged' ]
  service_offering:
    description:
      - Name or id of the service offering of the new virtual machine. If not set, first found service offering is used.
    required: false
    default: null
  template:
    description:
      - Name or id of the template to be used for creating the new virtual machine. Required when using C(state=created). Mutually exclusive with C(ISO) option.
    required: false
    default: null
  iso:
    description:
      - Name or id of the ISO to be used for creating the new virtual machine. Required when using C(state=created). Mutually exclusive with C(template) option.
    required: false
    default: null
  hypervisor:
    description:
      - Name the hypervisor to be used for creating the new virtual machine. Relevant when using C(state=created) and option C(ISO) is used. If not set, first found hypervisor will be used.
    required: false
    default: null
    choices: [ 'KVM', 'VMware', 'BareMetal', 'XenServer', 'LXC', 'HyperV', 'UCS', 'OVM' ]
  networks:
    description:
      - List of networks to use for the new virtual machine.
    required: false
    default: []
    aliases: [ 'network' ]
  disk_offering:
    description:
      - Name of the disk offering to be used.
    required: false
    default: null
  disk_size:
    description:
      - Disk size in GByte required if deploying virtual machine from ISO.
    required: false
    default: null
  security_groups:
    description:
      - List of security groups the virtual machine to be applied to.
    required: false
    default: []
    aliases: [ 'security_group' ]
  project:
    description:
      - Name of the project the virtual machine to be created in.
    required: false
    default: null
  zone:
    description:
      - Name of the zone in which the virtual machine shoud be created. If not set, default zone is used.
    required: false
    default: null
  ssh_key:
    description:
      - Name of the SSH key to be deployed on the new virtual machine.
    required: false
    default: null
  affinity_groups:
    description:
      - Affinity groups names to be applied to the new virtual machine.
    required: false
    default: null
    aliases: [ 'affinity_group' ]
  user_data:
    description:
      - Optional data (ASCII) that can be sent to the virtual machine upon a successful deployment. The data will be automatically base64 encoded, consider switching to HTTP_POST by using C(CLOUDSTACK_METHOD=post) to increase the HTTP_GET size limit of 2KB to 32 KB.
    required: false
    default: null
  poll_async:
    description:
      - Poll async jobs until job has finised.
    required: false
    default: true
'''

EXAMPLES = '''
---
# Create a virtual machine on CloudStack from an ISO
# NOTE: Offering and ISO names depending on the CloudStack configuration.
- local_action:
    module: cs_virtualmachine
    name: web-vm-1
    iso: Linux Debian 7 64-bit
    hypervisor: VMware
    service_offering: 1cpu_1gb
    disk_offering: PerfPlus Storage
    disk_size: '20'


# Create a virtual machine on Exoscale Public Cloud
- local_action:
    module: cs_virtualmachine
    name: web-vm-1
    template: Linux Debian 7 64-bit
    service_offering: Tiny
    ssh_key: john@example.com
  register: vm

- debug: msg='default ip {{ vm.default_ip }} and is in state {{ vm.vm_state }}'


# Stop a virtual machine, credentials used in $HOME/.cloudstack.ini
- local_action: cs_virtualmachine name=web-vm-1 state=stopped


# Start a virtual machine, credentials used in $HOME/.cloudstack.ini
- local_action: cs_virtualmachine name=web-vm-1 state=started


# Remove a virtual machine, credentials used in $HOME/.cloudstack.ini
- local_action: cs_virtualmachine name=web-vm-1 state=absent
'''

import base64

try:
    from cs import CloudStack, CloudStackException, read_config
    has_lib_cs = True
except ImportError:
    has_lib_cs = False

class AnsibleCloudStack:

    def __init__(self, module):
        if not has_lib_cs:
            module.fail_json(msg="python library cs required: pip install cs")

        self.module = module
        self._connect()

        self.project_id = None
        self.ip_address_id = None
        self.zone_id = None
        self.vm_id = None
        self.os_type_id = None
        self.hypervisor = None


    def _connect(self):
        api_key = self.module.params.get('api_key')
        api_secret = self.module.params.get('secret_key')
        api_url = self.module.params.get('api_url')
        api_http_method = self.module.params.get('api_http_method')

        if api_key and api_secret and api_url:
            self.cs = CloudStack(
                endpoint=api_url,
                key=api_key,
                secret=api_secret,
                method=api_http_method
                )
        else:
            self.cs = CloudStack(**read_config())


    def get_project_id(self):
        if self.project_id:
            return self.project_id

        project = self.module.params.get('project')
        if not project:
            return None

        projects = self.cs.listProjects()
        if projects:
            for p in projects['project']:
                if project in [ p['name'], p['displaytext'], p['id'] ]:
                    self.project_id = p['id']
                    return self.project_id
        self.module.fail_json(msg="project '%s' not found" % project)


    def get_ip_address_id(self):
        if self.ip_address_id:
            return self.ip_address_id

        ip_address = self.module.params.get('ip_address')
        if not ip_address:
            self.module.fail_json(msg="IP address param 'ip_address' is required")

        args = {}
        args['ipaddress'] = ip_address
        args['projectid'] = self.get_project_id()
        ip_addresses = self.cs.listPublicIpAddresses(**args)

        if not ip_addresses:
            self.module.fail_json(msg="IP address '%s' not found" % args['ipaddress'])

        self.ip_address_id = ip_addresses['publicipaddress'][0]['id']
        return self.ip_address_id


    def get_vm_id(self):
        if self.vm_id:
            return self.vm_id

        vm = self.module.params.get('vm')
        if not vm:
            self.module.fail_json(msg="Virtual machine param 'vm' is required")

        args = {}
        args['projectid'] = self.get_project_id()
        vms = self.cs.listVirtualMachines(**args)
        if vms:
            for v in vms['virtualmachine']:
                if vm in [ v['name'], v['displaytext'] v['id'] ]:
                    self.vm_id = v['id']
                    return self.vm_id
        self.module.fail_json(msg="Virtual machine '%s' not found" % vm)


    def get_zone_id(self):
        if self.zone_id:
            return self.zone_id

        zone = self.module.params.get('zone')
        zones = self.cs.listZones()

        # use the first zone if no zone param given
        if not zone:
            self.zone_id = zones['zone'][0]['id']
            return self.zone_id

        if zones:
            for z in zones['zone']:
                if zone in [ z['name'], z['id'] ]:
                    self.zone_id = z['id']
                    return self.zone_id
        self.module.fail_json(msg="zone '%s' not found" % zone)


    def get_os_type_id(self):
        if self.os_type_id:
            return self.os_type_id

        os_type = self.module.params.get('os_type')
        if not os_type:
            return None

        os_types = self.cs.listOsTypes()
        if os_types:
            for o in os_types['ostype']:
                if os_type in [ o['description'], o['id'] ]:
                    self.os_type_id = o['id']
                    return self.os_type_id
        self.module.fail_json(msg="OS type '%s' not found" % os_type)


    def get_hypervisor(self):
        if self.hypervisor:
            return self.hypervisor

        hypervisor = self.module.params.get('hypervisor')
        hypervisors = self.cs.listHypervisors()

        # use the first hypervisor if no hypervisor param given
        if not hypervisor:
            self.hypervisor = hypervisors['hypervisor'][0]['name']
            return self.hypervisor

        for h in hypervisors['hypervisor']:
            if hypervisor.lower() == h['name'].lower():
                self.hypervisor = h['name']
                return self.hypervisor
        self.module.fail_json(msg="Hypervisor '%s' not found" % hypervisor)


    def _poll_job(self, job=None, key=None):
        if 'jobid' in job:
            while True:
                res = self.cs.queryAsyncJobResult(jobid=job['jobid'])
                if res['jobstatus'] != 0 and 'jobresult' in res:
                    if 'errortext' in res['jobresult']:
                        self.module.fail_json(msg="Failed: '%s'" % res['jobresult']['errortext'])
                    if key and key in res['jobresult']:
                        job = res['jobresult'][key]
                    break
                time.sleep(2)
        return job


class AnsibleCloudStackVirtualMachine(AnsibleCloudStack):

    def __init__(self, module):
        AnsibleCloudStack.__init__(self, module)
        self.result = {
            'changed': False,
        }
        self.vm = None


    def get_service_offering_id(self):
        service_offering = self.module.params.get('service_offering')

        service_offerings = self.cs.listServiceOfferings()
        if service_offerings:
            if not service_offering:
                return service_offerings['serviceoffering'][0]['id']

            for s in service_offerings['serviceoffering']:
                if service_offering in [ s['name'], s['id'] ]:
                    return s['id']
        self.module.fail_json(msg="Service offering '%s' not found" % service_offering)


    def get_template_or_iso_id(self):
        template = self.module.params.get('template')
        iso = self.module.params.get('iso')

        if not template and not iso:
            self.module.fail_json(msg="Template or ISO is required.")

        if template and iso:
            self.module.fail_json(msg="Template are ISO are mutually exclusive.")

        if template:
            templates = self.cs.listTemplates(templatefilter='executable')
            if templates:
                for t in templates['template']:
                    if template in [ t['displaytext'], t['name'], t['id'] ]:
                        return t['id']
            self.module.fail_json(msg="Template '%s' not found" % template)

        elif iso:
            isos = self.cs.listIsos()
            if isos:
                for i in isos['iso']:
                    if iso i [ i['displaytext'], i['name'], i['id']:
                        return i['id']
            self.module.fail_json(msg="ISO '%s' not found" % iso)


    def get_disk_offering_id(self):
        disk_offering = self.module.params.get('disk_offering')

        if not disk_offering:
            return None

        disk_offerings = self.cs.listDiskOfferings()
        if disk_offerings:
            for d in disk_offerings['diskoffering']:
                if disk_offering in [ d['name'], d['id'] ]:
                    return d['id']
        self.module.fail_json(msg="Disk offering '%s' not found" % disk_offering)



    def get_vm(self):
        vm = self.get_vm():
        if not vm:
            vm_name = self.module.params.get('name')

            args = {}
            args['projectid'] = self.get_project_id()
            vms = self.cs.listVirtualMachines(**args)
            if vms:
                for v in vms['virtualmachine']:
                    if vm_name in [ v['name'], v['displayname'], v['id'] ]:
                        self.vm = v
                        break
        return self.vm


    def get_network_ids(self):
        network_names = self.module.params.get('networks')
        if not network_names:
            return None

        args = {}
        args['zoneid'] = self.get_zone_id()
        args['projectid'] = self.get_project_id()
        networks = self.cs.listNetworks(**args)

        network_ids = []
        if networks:
            for n in networks['network']:
                if n['name'] in network_names or n['id'] in network_names:
                    network_ids.append(n['id'])
        return network_ids


    def create_vm(self):
        vm = self.get_vm()
        if not vm:
            self.result['changed'] = True

            args = {}
            args['templateid']          = self.get_template_or_iso_id())
            args['zoneid']              = self.get_zone_id()
            args['serviceofferingid']   = self.get_service_offering_id()
            args['projectid']           = self.get_project_id()
            args['networkids']          = ','.join(self.get_network_ids())
            args['diskofferingid']      = self.get_disk_offering_id()
            args['hypervisor']          = self.get_hypervisor()

            args['name']                = self.module.params.get('name')
            args['group']               = self.module.params.get('group')
            args['keypair']             = self.module.params.get('ssh_key')
            args['size']                = self.module.params.get('disk_size')

            user_data = self.module.params.get('user_data')
            if user_data:
                args['userdata'] = base64.b64encode(user_data)

            display_name = self.module.params.get('display_name')
            if not display_name:
                display_name = args['name']
            args['displayname'] = display_name

            security_group_name_list = self.module.params.get('security_groups')
            security_group_names = ''
            if security_group_name_list:
                security_group_names = ','.join(security_group_name_list)
            args['securitygroupnames'] = security_group_names

            affinity_group_name_list = self.module.params.get('affinity_groups')
            affinity_group_names = ''
            if affinity_group_name_list:
                affinity_group_names = ','.join(affinity_group_name_list)
            args['affinitygroupnames'] = affinity_group_names

            if not self.module.check_mode:
                vm = self.cs.deployVirtualMachine(**args)

                if 'errortext' in vm:
                    self.module.fail_json(msg="Failed: '%s'" % vm['errortext'])

                poll_async = self.module.params.get('poll_async')
                if poll_async:
                    vm = self._poll_job(vm, 'virtualmachine')
        return vm


    def scale_vm(self):
        vm = self.get_vm()
        if vm:
            service_offering_id = self.get_service_offering_id()
            if vm['serviceofferingid'] != service_offering_id:
                self.result['changed'] = True
                if not self.module.check_mode:
                    vm_state = vm['state'].lower()
                    vm = self.stop_vm()
                    vm = self._poll_job(vm, 'virtualmachine')
                    self.cs.scaleVirtualMachine(id=vm['id'], serviceofferingid=service_offering_id)

                    # Start VM again if it ran before the scaling
                    if vm_state == 'running':
                        vm = self.start_vm()
                        vm = self._poll_job(vm, 'virtualmachine')
        return vm


    def remove_vm(self):
        vm = self.get_vm()
        if vm:
            if vm['state'].lower() not in [ 'expunging', 'destroying', 'destroyed' ]:
                self.result['changed'] = True
                if not self.module.check_mode:
                    res = self.cs.destroyVirtualMachine(id=vm['id'])

                    if 'errortext' in res:
                        self.module.fail_json(msg="Failed: '%s'" % res['errortext'])

                    poll_async = self.module.params.get('poll_async')
                    if poll_async:
                        vm = self._poll_job(res, 'virtualmachine')
        return vm


    def expunge_vm(self):
        vm = self.get_vm()
        if vm:
            res = {}
            if vm['state'].lower() in [ 'destroying', 'destroyed' ]:
                self.result['changed'] = True
                if not self.module.check_mode:
                    res = self.cs.expungeVirtualMachine(id=vm['id'])

            elif vm['state'].lower() not in [ 'expunging' ]:
                self.result['changed'] = True
                if not self.module.check_mode:
                    res = self.cs.destroyVirtualMachine(id=vm['id'], expunge=True)

            if res and 'errortext' in res:
                self.module.fail_json(msg="Failed: '%s'" % res['errortext'])

            poll_async = self.module.params.get('poll_async')
            if poll_async:
                vm = self._poll_job(res, 'virtualmachine')
        return vm


    def stop_vm(self):
        vm = self.get_vm()
        if not vm:
            self.module.fail_json(msg="Virtual machine named '%s' not found" % self.module.params.get('name'))

        if vm['state'].lower() == 'starting' and vm['state'].lower() != 'running':
            self.result['changed'] = True
            if not self.module.check_mode:
                vm = self.cs.stopVirtualMachine(id=vm['id'])

                if 'errortext' in vm:
                    self.module.fail_json(msg="Failed: '%s'" % vm['errortext'])

                poll_async = self.module.params.get('poll_async')
                if poll_async:
                    vm = self._poll_job(vm, 'virtualmachine')
        return vm


    def start_vm(self):
        vm = self.get_vm()
        if not vm:
            module.fail_json(msg="Virtual machine named '%s' not found" % module.params.get('name'))

        if vm['state'].lower() == 'stopped' or vm['state'].lower() == 'stopping':
            self.result['changed'] = True
            if not self.module.check_mode:
                vm = self.cs.startVirtualMachine(id=vm['id'])

                if 'errortext' in vm:
                    self.module.fail_json(msg="Failed: '%s'" % vm['errortext'])

                poll_async = self.module.params.get('poll_async')
                if poll_async:
                    vm = self._poll_job(vm, 'virtualmachine')

        return vm


    def restart_vm(self):
        vm = self.get_vm()
        if not vm:
            module.fail_json(msg="Virtual machine named '%s' not found" % self.module.params.get('name'))

        if vm['state'].lower() in [ 'running', 'starting' ]:
            self.result['changed'] = True
            if not self.module.check_mode:
                vm = self.cs.rebootVirtualMachine(id=vm['id'])
                poll_async = self.module.params.get('poll_async')
                if poll_async:
                    vm = self._poll_job(vm, 'virtualmachine')

        elif vm['state'].lower() in [ 'stopping', 'stopped' ]:
            self.module.fail_json(msg="Virtual machine named '%s' not running, not restarted" % self.module.params.get('name'))
        return vm


def main():
    module = AnsibleModule(
        argument_spec = dict(
            name = dict(required=True),
            group = dict(default=None),
            state = dict(choices=['created', 'started', 'stopped', 'restarted', 'present', 'absent', 'destroyed', 'expunged'], default='present'),
            service_offering = dict(default=None),
            template = dict(default=None),
            iso = dict(default=None),
            networks = dict(type='list', aliases= [ 'network' ], default=None),
            disk_offering = dict(default=None),
            disk_size = dict(default=None),
            hypervisor = dict(default=None),
            security_groups = dict(type='list', aliases= [ 'security_group' ], default=None),
            affinity_groups = dict(type='list', aliases= [ 'affinity_group' ], default=None),
            project = dict(default=None),
            user_data = dict(default=None),
            zone = dict(default=None),
            poll_async = dict(choices=BOOLEANS, default=True),
            ssh_key = dict(default=None),
            api_key = dict(default=None),
            api_secret = dict(default=None),
            api_url = dict(default=None),
            api_http_method = dict(default='get'),
        ),
        supports_check_mode=True
    )

    result = {}
    state = module.params.get('state')
    result['changed'] = False

    try:
        api_key = module.params.get('api_key')
        api_secret = module.params.get('secret_key')
        api_url = module.params.get('api_url')
        api_http_method = module.params.get('api_http_method')

        if api_key and api_secret and api_url:
            cs = CloudStack(
                endpoint=api_url,
                key=api_key,
                secret=api_secret,
                method=api_http_method
                )
        else:
            cs = CloudStack(**read_config())

        project_id = get_project_id(module, cs)
        vm = get_vm(module, cs, project_id)

        if state in ['absent', 'destroyed']:
            (result, vm) = remove_vm(module, cs, result, vm)

        elif state in ['expunged']:
            (result, vm) = expunge_vm(module, cs, result, vm)

        elif state in ['present', 'created']:
            if not vm:
                (result, vm) = create_vm(module, cs, result, vm, project_id)
            else:
                (result, vm) = scale_vm(module, cs, result, vm)

        elif state in ['stopped', 'halted']:
            (result, vm) = stop_vm(module, cs, result, vm)

        elif state in ['started', 'running', 'booted']:
            (result, vm) = start_vm(module, cs, result, vm)

        elif state in ['restarted', 'rebooted']:
            (result, vm) = restart_vm(module, cs, result, vm)

        if vm:

            if 'state' in vm and vm['state'] == 'Error':
                module.fail_json(msg="Virtual machine named '%s' in error state." % module.params.get('name'))

            if 'id' in vm:
                result['id'] = vm['id']

            if 'name' in vm:
                result['name'] = vm['name']

            if 'displayname' in vm:
                result['display_name'] = vm['displayname']

            if 'group' in vm:
                result['group'] = vm['group']

            if 'password' in vm:
                result['password'] = vm['password']

            if 'serviceofferingname' in vm:
                result['service_offering'] = vm['serviceofferingname']

            if 'zonename' in vm:
                result['zone'] = vm['zonename']

            if 'templatename' in vm:
                result['template'] = vm['templatename']

            if 'isoname' in vm:
                result['iso'] = vm['isoname']

            if 'created' in vm:
                result['created'] = vm['created']

            if 'state' in vm:
                result['vm_state'] = vm['state']

            if 'tags' in vm:
                tags = {}
                for tag in vm['tags']:
                    key = tag['key']
                    value = tag['value']
                    tags[key] = value
                result['tags'] = tags

            if 'nic' in vm:
                for nic in vm['nic']:
                    if nic['isdefault']:
                        result['default_ip'] = nic['ipaddress']
                result['nic'] = vm['nic']

    except CloudStackException, e:
        module.fail_json(msg='CloudStackException: %s' % str(e))

    module.exit_json(**result)

# import module snippets
from ansible.module_utils.basic import *
main()
