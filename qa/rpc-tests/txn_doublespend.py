#!/usr/bin/env python3
# Copyright (c) 2014-2016 The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or https://www.opensource.org/licenses/mit-license.php .

#
# Test proper accounting with malleable transactions
#

from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import assert_equal, connect_nodes, \
    sync_blocks, gather_inputs

from decimal import Decimal


class TxnMallTest(BitcoinTestFramework):

    def __init__(self):
        super().__init__()
        self.num_nodes = 4
        self.setup_clean_chain = False

    def add_options(self, parser):
        parser.add_option("--mineblock", dest="mine_block", default=False, action="store_true",
                          help="Test double-spend of 1-confirmed transaction")

    def setup_network(self):
        # Start with split network:
        return super(TxnMallTest, self).setup_network(True)

    def run_test(self):
        mining_reward = Decimal(100*0.97)
        starting_balance = Decimal(3920000*0.97) + mining_reward * 24
        starting_balance2 = mining_reward * 25

        for i in range(4):
            if i == 0:
                assert_equal(self.nodes[i].getbalance(), starting_balance)
            else:
                assert_equal(self.nodes[i].getbalance(), starting_balance2)
            self.nodes[i].getnewaddress("")  # bug workaround, coins generated assigned to first getnewaddress!

        # Coins are sent to node1_address
        node1_address = self.nodes[1].getnewaddress("")

        # First: use raw transaction API to send (starting_balance - (mining_reward - 2)) BTC to node1_address,
        # but don't broadcast:
        (total_in, inputs) = gather_inputs(self.nodes[0], (starting_balance - (mining_reward - 2)))
        change_address = self.nodes[0].getnewaddress("")
        outputs = {}
        outputs[change_address] = (mining_reward - 2)
        outputs[node1_address] = (starting_balance - (mining_reward - 2))
        rawtx = self.nodes[0].createrawtransaction(inputs, outputs)
        doublespend = self.nodes[0].signrawtransaction(rawtx)
        assert_equal(doublespend["complete"], True)

        # Create two transaction from node[0] to node[1]; the
        # second must spend change from the first because the first
        # spends all mature inputs:
        txid1 = self.nodes[0].sendtoaddress(node1_address, (starting_balance - (mining_reward - 2)))
        txid2 = self.nodes[0].sendtoaddress(node1_address, 5)

        # Have node0 mine a block:
        if (self.options.mine_block):
            self.nodes[0].generate(1)
            sync_blocks(self.nodes[0:2])

        tx1 = self.nodes[0].gettransaction(txid1)
        tx2 = self.nodes[0].gettransaction(txid2)

        # Node0's balance should be starting balance, plus mining_reward for another
        # matured block, minus (starting_balance - (mining_reward - 2)), minus 5, and minus transaction fees:
        expected = Decimal(starting_balance)
        if self.options.mine_block: expected += mining_reward
        expected += tx1["amount"] + tx1["fee"]
        expected += tx2["amount"] + tx2["fee"]
        assert_equal(self.nodes[0].getbalance(), expected)

        if self.options.mine_block:
            assert_equal(tx1["confirmations"], 1)
            assert_equal(tx2["confirmations"], 1)
            # Node1's total balance should be its starting balance plus both transaction amounts:
            assert_equal(self.nodes[1].getbalance(""), starting_balance - (tx1["amount"]+tx2["amount"]))
        else:
            assert_equal(tx1["confirmations"], 0)
            assert_equal(tx2["confirmations"], 0)

        # Now give doublespend to miner:
        self.nodes[2].sendrawtransaction(doublespend["hex"])
        # ... mine a block...
        self.nodes[2].generate(1)

        # Reconnect the split network, and sync chain:
        connect_nodes(self.nodes[1], 2)
        self.nodes[2].generate(1)  # Mine another block to make sure we sync
        sync_blocks(self.nodes)

        # Re-fetch transaction info:
        tx1 = self.nodes[0].gettransaction(txid1)
        tx2 = self.nodes[0].gettransaction(txid2)

        # Both transactions should be conflicted
        assert_equal(tx1["confirmations"], -1)
        assert_equal(tx2["confirmations"], -1)

        # Node0's total balance should be starting balance, plus (mining_reward * 2) for
        # two more matured blocks, minus (starting_balance - (mining_reward - 2)) for the double-spend:
        expected = starting_balance + (mining_reward * 2) - (starting_balance - (mining_reward - 2))
        assert_equal(self.nodes[0].getbalance(), expected)
        assert_equal(self.nodes[0].getbalance("*"), expected)

        # Node1's total balance should be its starting balance plus the amount of the mutated send:
        assert_equal(self.nodes[1].getbalance(""), starting_balance + (starting_balance2 - (mining_reward - 2)))

if __name__ == '__main__':
    TxnMallTest().main()
