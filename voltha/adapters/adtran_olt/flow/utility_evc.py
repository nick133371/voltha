# Copyright 2017-present Adtran, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from voltha.core.flow_decomposer import *
from evc import EVC
from twisted.internet import defer
from twisted.internet.defer import returnValue, inlineCallbacks

log = structlog.get_logger()

EVC_NAME_FORMAT = 'VOLTHA-UTILITY-{}'                   # format(flow.vlan_id)
EVC_NAME_REGEX_ALL = EVC_NAME_FORMAT.format('*')


_utility_evcs = {}  # device-id -> flow dictionary
                    #                  |
                    #                  +-> untagged-vlan-id -> evcs


class UtilityEVC(EVC):
    """
    Class to wrap orphan ingress ACLs EVC functionality
    """
    def __init__(self, flow_entry):
        super(UtilityEVC, self).__init__(flow_entry)
        self._downstream_flows = {flow_entry.flow_id}     # Matching Downstream Flow IDs
        self.service_evc = True

    def __str__(self):
        return "VOLTHA-UTILITY-{}: MEN: {}, VLAN: {}".format(self._name, self._men_ports, self._s_tag)

    def _create_name(self):
        #
        # TODO: Take into account selection criteria and output to make the name
        #
        return EVC_NAME_FORMAT.format(self._flow.vlan_id)

    @staticmethod
    def create(flow_entry):
        device_id = flow_entry.device_id
        evc_table = _utility_evcs.get(device_id)

        if evc_table is None:
            _utility_evcs[device_id] = dict()
            evc_table = _utility_evcs[device_id]

        try:
            evc = evc_table.get(flow_entry.vlan_id)

            if evc is None:
                # Create EVC and initial EVC Map
                evc = UtilityEVC(flow_entry)
                evc_table[flow_entry.vlan_id] = evc
            else:
                if flow_entry.flow_id in evc.downstream_flows:    # TODO: Debug only to see if flow_ids are unique
                    pass
                else:
                    evc.add_downstream_flows(flow_entry.flow_id)

            return evc

        except Exception as e:
            log.exception('untagged-create', e=e)
            return None

    @property
    def flow_entry(self):
        return self._flow

    @property
    def downstream_flows(self):
        return frozenset(self._downstream_flows)

    def add_downstream_flows(self, flow_id):
        self._downstream_flows.add(flow_id)

    def remove_downstream_flows(self, flow_id):
        self._downstream_flows.discard(flow_id)

    @inlineCallbacks
    def remove(self, remove_maps=True):
        """
        Remove EVC (and optional associated EVC-MAPs) from hardware
        :param remove_maps: (boolean)
        :return: (deferred)
        """
        log.info('removing', evc=self, remove_maps=remove_maps)

        device_id = self._handler.device_id
        flow_id = self._flow.id
        evc_table = _utility_evcs.get(device_id)

        if evc_table is None or flow_id not in evc_table:
            returnValue('NOP')

        # Remove flow reference
        if self._flow.flow_id in self._downstream_flows:
            del self._downstream_flows[self._flow.flow_id]

        if len(self._downstream_flows) == 0:
            # Use base class to clean up
            returnValue(super(UtilityEVC, self).remove(remove_maps=True))

        returnValue('More references')

    @inlineCallbacks
    def delete(self, delete_maps=True):
        """
        Remove from hardware and delete/clean-up EVC Object
        """
        log.info('deleting', evc=self, delete_maps=delete_maps)

        try:
            dl = [self.remove()]
            if delete_maps:
                for evc_map in self.evc_maps:
                    dl.append(evc_map.delete(None))   # TODO: implement bulk-flow procedures

            yield defer.gatherResults(dl, consumeErrors=True)

        except Exception as e:
            log.exception('removal', e=e)

        self._evc_maps = None
        f, self._flow = self._flow, None
        if f is not None and f.handler is not None:
            f.handler.remove_evc(self)

    def reflow(self, reflow_maps=True):
        pass    # TODO: Implement or use base class?

    @staticmethod
    def remove_all(client, regex_=EVC_NAME_REGEX_ALL):
        """
        Remove all matching EVCs from hardware
        :param client: (ncclient) NETCONF Client to use
        :param regex_: (String) Regular expression for name matching
        :return: (deferred)
        """
        pass    # TODO: ???