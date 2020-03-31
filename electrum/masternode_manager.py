from collections import namedtuple, OrderedDict
import base64
import threading
from decimal import Decimal

from .constants import COLLATERAL_COINS
from . import bitcoin
from . import ecc
from .blockchain import hash_header
from .masternode import MasternodeAnnounce, NetworkAddress, MasternodePing
from .masternode_budget import BudgetProposal, BudgetVote
from .util import AlreadyHaveAddress, bfh, bh2u
from .util import format_satoshis_plain
from .logging import get_logger

###john
import random
import copy

#from electrum.gui.kivy.i18n import _

_logger = get_logger(__name__)


BUDGET_FEE_CONFIRMATIONS = 6
BUDGET_FEE_TX = 5 * bitcoin.COIN
# From masternode.h
MASTERNODE_MIN_CONFIRMATIONS = 15

MasternodeConfLine = namedtuple('MasternodeConfLine', ('alias', 'addr',
        'wif', 'txid', 'output_index'))

def parse_masternode_conf(lines):
    """Construct MasternodeConfLine instances from lines of a masternode.conf file."""
    conf_lines = []
    for line in lines:
        # Comment.
        if line.startswith('#'):
            continue

        s = line.split(' ')
        if len(s) < 5:
            continue
        alias = s[0]
        addr_str = s[1]
        masternode_wif = s[2]
        collateral_txid = s[3]
        collateral_output_n = s[4]

        # Validate input.
        try:
            txin_type, key, is_compressed = bitcoin.deserialize_privkey(masternode_wif)
            assert key
        except Exception:
            raise ValueError('Invalid masternode private key of alias "%s"' % alias)

        if len(collateral_txid) != 64:
            raise ValueError('Transaction ID of alias "%s" must be 64 hex characters.' % alias)

        try:
            collateral_output_n = int(collateral_output_n)
        except ValueError:
            raise ValueError('Transaction output index of alias "%s" must be an integer.' % alias)

        conf_lines.append(MasternodeConfLine(alias, addr_str, masternode_wif, collateral_txid, collateral_output_n))
    return conf_lines

def parse_proposals_subscription_result(results):
    """Parse the proposals subscription response."""
    proposals = []
    for k, result in results.items():
        kwargs = {'proposal_name': result['Name'], 'proposal_url': result['URL'],
                'start_block': int(result['BlockStart']), 'end_block': int(result['BlockEnd']),
                'payment_amount': result['MonthlyPayment'], 'address': result['PaymentAddress']}

        fee_txid_key = 'FeeTXHash' if result.get('FeeTXHash') else 'FeeHash'
        kwargs['fee_txid'] = result[fee_txid_key]
        yes_count_key = 'YesCount' if result.get('YesCount') else 'Yeas'
        kwargs['yes_count'] = result[yes_count_key]
        no_count_key = 'NoCount' if result.get('NoCount') else 'Nays'
        kwargs['no_count'] = result[no_count_key]

        payment_amount = Decimal(str(kwargs['payment_amount']))
        kwargs['payment_amount'] = pow(10, 8) * payment_amount
        proposals.append(BudgetProposal.from_dict(kwargs))

    _logger.info(f'Received updated budget proposal information '
                 f'({len(proposals)} proposals)')
    return proposals

class MasternodeManager(object):
    """Masternode manager.

    Keeps track of masternodes and helps with signing broadcasts.
    """
    def __init__(self, wallet, config):
        self.network_event = threading.Event()
        self.wallet = wallet
        self.config = config
        # Subscribed masternode statuses.
        self.masternode_statuses = {}
        self.subcribe_height = 0
        self.test = True
        self.load()
    
    def set_wallet(self, wallet):
        self.wallet = wallet
        self.load()
    
    def load(self):
        """Load masternodes from wallet storage."""
        self.masternodes= {}        
        if self.wallet is None:
            return
        
        masternodes = self.wallet.storage.get('masternodes', {})
        for key in masternodes.keys():
            mn = masternodes[key]        
            self.masternodes[key] = MasternodeAnnounce.from_dict(mn)
        
        proposals = self.wallet.storage.get('budget_proposals', {})        
        self.proposals = [BudgetProposal.from_dict(d) for d in proposals.values()]
        self.budget_votes = [BudgetVote.from_dict(d) for d in self.wallet.storage.get('budget_votes', [])]

    def send_subscriptions(self):
        if not self.wallet.network.is_connected():
            return
        self.subscribe_to_masternodes1()

    def subscribe_to_masternodes(self):
        for key in self.masternodes.keys():
            mn = self.masternodes[key]
            collateral = mn.get_collateral_str()
            if not '-' in collateral or len(collateral.split('-')[0]) != 64:
                continue
            if self.masternode_statuses.get(collateral) is None:
                network = self.wallet.network
                method = network.interface.session.send_request
                request = ('masternode.subscribe', [collateral])
                async def update_collateral_status():
                    self.masternode_statuses[collateral] = ''
                    try:
                        res = await method(*request)
                        response = {'params': request[1], 'result': res}
                        self.masternode_subscription_response(response)
                    except Exception as e:
                        _logger.info(f'subscribe_to_masternodes: {repr(e)}')
                network.run_from_another_thread(update_collateral_status())

    def get_masternode(self, collateral):
        """Get the masternode labelled as alias."""
        for key in self.masternodes.keys():
            if key == collateral:
                return self.masternodes[key]

    def get_masternode_by_hash(self, hash_):
        for key in self.masternodes.keys():
            mn = self.masternodes[key]
            if mn.get_hash() == hash_:
                return mn
            
    def isexist_from_name(self, mn):
        for key in self.masternodes.keys():
            if mn.alias == self.masternodes[key].alias :
                return True, mn.alias
        return False, mn.alias        
    
    def isexist_from_delegate(self, mn):
        for key in self.masternodes.keys():
            if mn.delegate_key == self.masternodes[key].delegate_key :
                return True, mn.delegate_key
        return False, mn.delegate_key
    
    def add_masternode(self, mn, save = True):
        """Add a new masternode."""
        key = mn.vin['prevout_hash'] + '-' + str(mn.vin['prevout_n'])
        mn1 = self.masternodes.get(key)
        
        isexist, alias = self.isexist_from_name(mn)
        if isexist:
            raise Exception('A masternode with alias "%s" already exists' % alias)        
        if mn.delegate_key != '':
            isexist, delegate = self.isexist_from_delegate(mn)            
            if isexist:
                raise Exception('A masternode with Private Key "%s" already exists' % self.parent.wallet.get_delegate_private_key(delegate_key))                    
        
        if  mn1 is None:
            self.masternodes[key] = mn
        else:
            if mn1.delegate_key == mn.delegate_key:                
                raise Exception('A masternode with Private Key "%s" already exists' % self.parent.wallet.get_delegate_private_key(mn.delegate_key))
            self.masternodes[key] = mn
        if save:
            self.save()

    def remove_masternode(self, collateral, save = True):
        """Remove the masternode labelled as alias."""
        mn = self.get_masternode(collateral)
        if not mn:
            raise Exception('Nonexistent masternode')
        # Don't delete the delegate key if another masternode uses it too.
        bDel = True
        for key in self.masternodes.keys():
            mn1 = self.masternodes[key]
            if (mn1.alias != mn.alias and mn1.delegate_key == mn.delegate_key):
                bDel = False
                break
        
        if bDel:        
            self.wallet.delete_masternode_delegate(mn.delegate_key)
        
        self.masternodes.pop(collateral)
        if save:
            self.save()
            
    def populate_masternode_output(self, alias):
        """Attempt to populate the masternode's data using its output."""
        mn = self.get_masternode(alias)
        if not mn:
            return
        if mn.announced:
            return
        txid = mn.vin.get('prevout_hash')
        prevout_n = mn.vin.get('prevout_n')
        if not txid or prevout_n is None:
            return
        # Return if it already has the information.
        if mn.collateral_key and mn.vin.get('address') and mn.vin.get('value') == COLLATERAL_COINS * bitcoin.COIN:
            return
        ###john
        
        tx = self.wallet.db.get_transaction(txid)
        if not tx:
            return
        if len(tx.outputs()) <= prevout_n:
            return
        _, addr, value, _, _ = tx.outputs()[prevout_n]
        
        mn.collateral_key = self.wallet.get_public_keys(addr)[0]
        self.save()
        return True

    def get_masternode_outputs(self, domain = None, exclude_frozen = True):
        """Get spendable coins that can be used as masternode collateral."""
        excluded = self.wallet.frozen_addresses if exclude_frozen else None
        coins = self.wallet.get_utxos(domain, excluded_addresses=excluded,
                                      mature_only=True, confirmed_only=True)
        
        
        '''
        used_vins = map(lambda key: '%s:%d' % (self.masternodes[key].vin.get('prevout_hash'), self.masternodes[key].vin.get('prevout_n', 0xffffffff)), self.masternodes.keys())
        unused = lambda d: '%s:%d' % (d['prevout_hash'], d['prevout_n']) not in used_vins
        correct_amount = lambda d: d['value'] == COLLATERAL_COINS * bitcoin.COIN

        # Valid outputs have a value of exactly 1000 VOLLAR and
        # are not in use by an existing masternode.
        is_valid = lambda d: correct_amount(d) and unused(d)

        coins = filter(is_valid, coins)
        '''
        
        return coins

    def get_delegate_privkey(self, pubkey):
        """Return the private delegate key for pubkey (if we have it)."""
        return self.wallet.get_delegate_private_key(pubkey)

    def check_can_sign_masternode(self, collateral):
        """Raise an exception if alias can't be signed and announced to the network."""
        mn = self.get_masternode(collateral)
        if not mn:
            raise Exception('Nonexistent masternode')
        if not mn.vin.get('prevout_hash'):
            raise Exception('Collateral payment is not specified')
        if not mn.collateral_key:
            raise Exception('Collateral key is not specified')
        if not mn.delegate_key:
            raise Exception('Masternode delegate key is not specified')
        if not mn.addr.ip:
            raise Exception('Masternode has no IP address')

        # Ensure that the collateral payment has >= MASTERNODE_MIN_CONFIRMATIONS.
        tx_height = self.wallet.get_tx_height(mn.vin['prevout_hash'])
        if tx_height.conf < MASTERNODE_MIN_CONFIRMATIONS:
            raise Exception('Collateral payment must have at least %d '
                            'confirmations (current: %d)' %
                            (MASTERNODE_MIN_CONFIRMATIONS, tx_height.conf))
        # Ensure that the masternode's vin is valid.
        if mn.vin.get('value', 0) != bitcoin.COIN * COLLATERAL_COINS:
            raise Exception('Masternode requires a collateral 10000 VOLLAR output.')

        # If the masternode has been announced, it can be announced again if it has been disabled.
        if mn.announced:
            status = self.masternode_statuses.get(mn.get_collateral_str())
            if status in ['PRE_ENABLED', 'ENABLED']:
                raise Exception('Masternode has already been activated')

    def save(self):
        """Save masternodes."""
        masternodes = {}
        for key in self.masternodes.keys():
            mn = self.masternodes[key]
            masternodes[key] = mn.dump()
            
        proposals = {p.get_hash(): p.dump() for p in self.proposals}
        votes = [v.dump() for v in self.budget_votes]

        self.wallet.storage.put('masternodes', masternodes)        
        self.wallet.storage.put('budget_proposals', proposals)
        self.wallet.storage.put('budget_votes', votes)

    def sign_announce(self, key, password):
        """Sign a Masternode Announce message for alias."""        
        #self.check_can_sign_masternode(alias)
        mn = self.get_masternode(key)
        # Ensure that the masternode's vin is valid.
        if mn.vin.get('scriptSig') is None:
            mn.vin['scriptSig'] = ''
        if mn.vin.get('sequence') is None:
            mn.vin['sequence'] = 0xffffffff
        # Ensure that the masternode's last_ping is current.
        height = self.wallet.get_local_height() - 12
        blockchain = self.wallet.network.blockchain()
        header = blockchain.read_header(height)
        mn.last_ping.block_hash = hash_header(header)
        mn.last_ping.vin = mn.vin

        # Sign ping with delegate key.
        self.wallet.sign_masternode_ping(mn.last_ping, mn.delegate_key)

        # After creating the Masternode Ping, sign the Masternode Announce.
        address = bitcoin.public_key_to_p2pkh(bfh(mn.collateral_key))
        ######john
        mn.sig = self.wallet.sign_masternode_message(address, mn.serialize_for_sig(update_time=True), password)
        print("address:", address)
        print("announce sig:", base64.b64encode(mn.sig))
        return mn

    def send_announce(self, key):
        """Broadcast a Masternode Announce message for alias to the network.

        Returns a 2-tuple of (error_message, was_announced).
        """
        if not self.wallet.network.is_connected():
            raise Exception('Not connected')

        mn = self.get_masternode(key)
        # Vector-serialize the masternode.
        serialized = '01' + mn.serialize()
        print(serialized)
        errmsg = []

        self.network_event.clear()
        network = self.wallet.network
        method = network.interface.session.send_request
        request = ('masternode.announce.broadcast', [serialized])
        async def masternode_announce_broadcast():
            try:
                r = {}
                r['result'] = await method(*request)
            except Exception as e:
                r['result'] = {}
                r['error'] = str(e)
            try:
                self.on_broadcast_announce(key, r)
            except Exception as e:
                errmsg.append(str(e))
            finally:
                self.save()
                self.network_event.set()
        network.run_from_another_thread(masternode_announce_broadcast())
        self.network_event.wait()
        self.subscribe_to_masternodes()
        if errmsg:
            errmsg = errmsg[0]
        return (errmsg, mn.announced)

    def on_broadcast_announce(self, key, r):
        """Validate the server response."""
        err = r.get('error')
        if err:
            raise Exception('Error response: %s' % str(err))

        result = r.get('result')

        mn = self.get_masternode(key)
        mn_hash = mn.get_hash()
        mn_dict = result.get(mn_hash)
        if not mn_dict:
            raise Exception('No result for expected Masternode Hash. Got %s' % result)

        if mn_dict.get('errorMessage'):
            raise Exception('Announce was rejected: %s' % mn_dict['errorMessage'])
        if mn_dict.get(mn_hash) != 'successful':
            raise Exception('Announce was rejected (no error message specified)')

        mn.announced = True

    def import_masternode_delegate(self, sec):
        """Import a WIF delegate key.

        An exception will not be raised if the key is already imported.
        """
        try:
            pubkey = self.wallet.import_masternode_delegate(sec)
        except AlreadyHaveAddress:
            txin_type, key, is_compressed = bitcoin.deserialize_privkey(sec)
            pubkey = ecc.ECPrivkey(key)\
                .get_public_key_hex(compressed=is_compressed)
        return pubkey

    def import_masternode_conf_lines(self, conf_lines, password):
        """Import a list of MasternodeConfLine."""
        def already_have(line):
            for key in self.masternodes.keys():
                masternode = self.masternodes[key]
                # Don't let aliases collide.
                if masternode.alias == line.alias:
                    return True
                # Don't let outputs collide.
                if masternode.vin.get('prevout_hash') == line.txid and masternode.vin.get('prevout_n') == line.output_index:
                    return True
            return False

        num_imported = 0
        for conf_line in conf_lines:
            if already_have(conf_line):
                continue
            addr = conf_line.addr.split(':')
            addr = NetworkAddress(ip=addr[0], port=int(addr[1]))
            vin = {'prevout_hash': conf_line.txid, 'prevout_n': conf_line.output_index}
            
            ret, collateral = self.get_transaction(vin['prevout_hash'], vin['prevout_n'])
            if not ret:
                continue
                
            try:
                collateral = self.wallet.get_public_keys(collateral)[0]       
            except Exception as e:
                collateral = ''
                continue
                
            try:
                delegate = self.import_masternode_delegate(conf_line.wif)
            except Exception as e:
                continue
                            
            mn = MasternodeAnnounce(alias=conf_line.alias, vin=vin, collateral_key= collateral, 
                    delegate_key = delegate, addr=addr)
            self.add_masternode(mn)
            try:
                self.populate_masternode_output(mn.alias)
            except Exception as e:
                _logger.info(str(e))
            num_imported += 1

        return num_imported

    def get_votes(self, alias):
        """Get budget votes that alias has cast."""
        mn = self.get_masternode(alias)
        if not mn:
            raise Exception('Nonexistent masternode')
        return filter(lambda v: v.vin == mn.vin, self.budget_votes)

    def check_can_vote(self, alias, proposal_name):
        """Raise an exception if alias can't vote for proposal name."""
        if not self.wallet.network.is_connected():
            raise Exception('Not connected')
        # Get the proposal that proposal_name identifies.
        proposal = None
        for p in self.wallet.network.all_proposals:
            if p.proposal_name == proposal_name:
                proposal = p
                break
        else:
            raise Exception('Unknown proposal')

        # Make sure the masternode hasn't already voted.
        proposal_hash = proposal.get_hash()
        previous_votes = self.get_votes(alias)
        if any(v.proposal_hash == proposal_hash for v in previous_votes):
            raise Exception('Masternode has already voted on this proposal')

        mn = self.get_masternode(alias)
        if not mn.announced:
            raise Exception('Masternode has not been activated')
        else:
            status = self.masternode_statuses.get(mn.get_collateral_str())
            if status not in ['PRE_ENABLED', 'ENABLED']:
                raise Exception('Masternode is not currently enabled')
        return proposal

    def vote(self, alias, proposal_name, vote_choice):
        """Vote on a budget proposal."""
        proposal = self.check_can_vote(alias, proposal_name)
        # Validate vote choice.
        if vote_choice.upper() not in ('YES', 'NO'):
            raise ValueError('Invalid vote choice: "%s"' % vote_choice)

        # Create the vote.
        mn = self.get_masternode(alias)
        vote = BudgetVote(vin=mn.vin, proposal_hash=proposal.get_hash(),
                          vote=vote_choice)

        # Sign the vote with delegate key.
        sig = self.wallet.sign_budget_vote(vote, mn.delegate_key)

        return self.send_vote(vote, base64.b64encode(sig))

    def send_vote(self, vote, sig):
        """Broadcast vote to the network.

        Returns a 2-tuple of (error_message, success).
        """
        errmsg = []
        params = [vote.vin['prevout_hash'],
                  vote.vin['prevout_n'],
                  vote.proposal_hash, vote.vote.lower(),
                  vote.timestamp, sig]
        self.network_event.clear()
        network = self.wallet.network
        method = network.interface.session.send_request
        request = ('masternode.budget.submitvote', params)
        async def masternode_budget_submitvote():
            try:
                r = {}
                r['result'] = await method(*request)
            except Exception as e:
                r['result'] = {}
                r['error'] = str(e)
            if r.get('error'):
                errmsg.append(r['error'])
            else:
                self.budget_votes.append(vote)
                self.save()
            self.network_event.set()
        network.run_from_another_thread(masternode_budget_submitvote())
        self.network_event.wait()
        if errmsg:
            return (errmsg[0], False)
        return (errmsg, True)

    def get_proposal(self, name):
        for proposal in self.proposals:
            if proposal.proposal_name == name:
                return proposal

    def add_proposal(self, proposal, save = True):
        """Add a new proposal."""
        if proposal in self.proposals:
            raise Exception('Proposal already exists')
        self.proposals.append(proposal)
        if save:
            self.save()

    def remove_proposal(self, proposal_name, save = True):
        """Remove the proposal named proposal_name."""
        proposal = self.get_proposal(proposal_name)
        if not proposal:
            raise Exception('Proposal does not exist')
        self.proposals.remove(proposal)
        if save:
            self.save()

    def create_proposal_tx(self, proposal_name, password, save = True):
        """Create a fee transaction for proposal_name."""
        proposal = self.get_proposal(proposal_name)
        if proposal.fee_txid:
            _logger.info(f'Warning: Proposal "{proposal_name}" already '
                         f'has a fee tx: {proposal.fee_txid}')
        if proposal.submitted:
            raise Exception('Proposal has already been submitted')

        h = bfh(bitcoin.hash_decode(proposal.get_hash()))
        script = '6a20' + h # OP_RETURN hash
        outputs = [(bitcoin.TYPE_SCRIPT, bfh(script), BUDGET_FEE_TX)]
        tx = self.wallet.mktx(outputs, password, self.config)
        proposal.fee_txid = tx.hash()
        if save:
            self.save()
        return tx

    def submit_proposal(self, proposal_name, save = True):
        """Submit the proposal for proposal_name."""
        proposal = self.get_proposal(proposal_name)
        if not proposal.fee_txid:
            raise Exception('Proposal has no fee transaction')
        if proposal.submitted:
            raise Exception('Proposal has already been submitted')

        if not self.wallet.network.is_connected():
            raise Exception('Not connected')

        tx_height = self.wallet.get_tx_height(proposal.fee_txid)
        if tx_height.conf < BUDGET_FEE_CONFIRMATIONS:
            raise Exception('Collateral requires at least %d confirmations' % BUDGET_FEE_CONFIRMATIONS)

        payments_count = proposal.get_payments_count()
        payment_amount = format_satoshis_plain(proposal.payment_amount)
        params = [proposal.proposal_name,
                  proposal.proposal_url,
                  payments_count,
                  proposal.start_block,
                  proposal.address,
                  payment_amount,
                  proposal.fee_txid]
        errmsg = []
        self.network_event.clear()
        network = self.wallet.network
        method = network.interface.session.send_request
        request = ('masternode.budget.submit', params)
        async def masternode_budget_submit():
            try:
                r = {}
                r['result'] = await method(*request)
            except Exception as e:
                r['result'] = {}
                r['error'] = str(e)
            try:
                self.on_proposal_submitted(proposal.proposal_name, r)
            except Exception as e:
                errmsg.append(str(e))
            finally:
                if save:
                    self.save()
                self.network_event.set()
        network.run_from_another_thread(masternode_budget_submit())
        self.network_event.wait()
        if errmsg:
            errmsg = errmsg[0]
        return (errmsg, proposal.submitted)

    def on_proposal_submitted(self, proposal_name, r):
        """Validate the server response."""
        proposal = self.get_proposal(proposal_name)
        err = r.get('error')
        if err:
            proposal.rejected = True
            raise Exception('Error response: %s' % str(err))

        result = r.get('result')

        if proposal.get_hash() != result:
            raise Exception('Invalid proposal hash from server: %s' % result)

        proposal.submitted = True

    def masternode_subscription_response(self, response):
        """Callback for when a masternode's status changes."""
        collateral = response['params'][0]
        mn = None
        for key in self.masternodes.keys():
            masternode = self.masternodes[key]
            if masternode.get_collateral_str() == collateral:
                mn = masternode
                break

        if not mn:
            return

        if not 'result' in response:
            return

        status = response['result']
        if status is None:
            status = False
        _logger.info(f'Received updated status for masternode '
                     f'{mn.alias}: "{status}"')
        self.masternode_statuses[collateral] = status
        
    ###john
    def is_used_masternode_from_coin(self, coin):
        key = coin.get('prevout_hash') + '-' + str(coin.get('prevout_n'))
        mn = self.masternodes.get(key)
        if mn is None and coin['value'] == COLLATERAL_COINS * bitcoin.COIN:
            return False       
        return True

    def is_used_masternode_from_host(self, host):
        ip, port = host.split(":")
        for key in self.masternodes.keys():
            mn = self.masternodes[key]
            if mn.addr.ip == ip and mn.addr.port == int(port):
                return True
        return False

    def get_default_alias(self):
        while True:
            alias = 'mn-' + str(int(random.random()*10000))
            if any(self.masternodes[key].alias == alias for key in self.masternodes.keys()):
                continue
            return alias

    def subscribe_to_masternodes1(self):
        local_height = self.blockchain.height()
        if self.subcribe_height >= local_height - 5:
            return
        self.subcribe_height = local_height                    
        for mn in self.masternodes:
            collateral = mn.get_collateral_str()
            if not '-' in collateral or len(collateral.split('-')[0]) != 64:
                continue
            if not (self.masternode_statuses.get(collateral)) is None:
                network = self.wallet.network
                method = network.interface.session.send_request
                request = ('masternode.subscribe', [collateral])
                async def update_collateral_status():
                    self.masternode_statuses[collateral] = ''
                    try:
                        res = await method(*request)
                        response = {'params': request[1], 'result': res}
                        self.masternode_subscription_response(response)
                    except Exception as e:
                        _logger.info(f'subscribe_to_masternodes: {repr(e)}')
                network.run_from_another_thread(update_collateral_status())
 
    def update_masternodes_status(self, update=False):
        local_height = self.wallet.get_local_height()
        if not update:
            if self.subcribe_height >= local_height - 5 :
                return            
        self.subcribe_height = local_height   
        collateral = []
        for key in self.masternodes.keys():
            mn = self.masternodes[key]
            address = bitcoin.public_key_to_p2pkh(bfh(mn.collateral_key))
            collateral.append(address)
            
        if len(self.masternodes) > 0:
            network = self.wallet.network            
            method = network.interface.session.send_request
            request = ('masternode.list', [collateral])            
            async def update_collateral_status():
                try:
                    res = await method(*request)
                    self.show_masternode_status(res)
                except Exception as e:
                    _logger.info(f'list_to_masternodes: {repr(e)}')
    
            network.run_from_another_thread(update_collateral_status())
     
    def get_transaction(self, txid, index):
        tx = self.wallet.db.get_transaction(txid)
        if not tx:
            return
        ctx = copy.deepcopy(tx)  # type: Transaction
        try:
            ctx.deserialize()
        except BaseException as e:
            raise SerializationError(e)
        
        outputs = ctx._outputs[index]
        address = outputs.address
        if outputs.value != COLLATERAL_COINS * bitcoin.COIN:
            return False, address
        
        return True, address
        
    def show_masternode_status(self, response):
        for mn in response:
            mn1 = self.masternodes.get(mn['vin'])
            if mn1 is None:
                continue
            
            mn1.status = mn['status']
            mn1.lastseen = int(mn['lastseen'])
            mn1.activeseconds = int(mn['activeseconds'])
            ip, port = mn['ip'].split(":")
            mn1.addr = NetworkAddress(ip=ip, port=int(port))
            
            self.save()
            
    def check_register(self, register_info, mobilephone, password, password1, bregister):        
        if bregister:
            if password != password1:
                raise Exception("password is not equal")
            
        if len(password) < 3:
            raise Exception("password length >=8")
        
        if len(mobilephone) < 11:
            raise Exception("mobilephone length >=8")

        if bregister:
            if not (register_info is None):
                raise Exception("mobilephone is have register")
            address = self.wallet.create_new_address(False)            
            self.wallet.storage.put('masternoderegister', {mobilephone:(password, address)})
            return address
            
        if register_info.get(mobilephone) is None:
            raise Exception("no register")
        
        pw , address = register_info.get(mobilephone)        
        if pw != password:
            raise Exception("password incorrect")
        
        return address