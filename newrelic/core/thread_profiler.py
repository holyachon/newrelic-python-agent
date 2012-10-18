import sys
import time
import threading
import zlib
import base64
import traceback

from newrelic.api.transaction import Transaction

try:
    from collections import namedtuple
except:
    from newrelic.lib.namedtuple import namedtuple

import newrelic.lib.simplejson as simplejson

_MethodData = namedtuple('_MethodData',
        ['file_name', 'method_name', 'line_no'])

NODE_LIMIT = 2000

class ProfileNode(object):
    """This class provides the node used to construct the call tree.
    """
    node_count = 0
    def __init__(self, method_data):
        self.method = method_data
        self.call_count = 0
        self.non_call_count = 0
        self.children = {}
        self.ignore = False
        ProfileNode.node_count += 1

    def get_or_create_child(self, method_data):
        """
        Return the child node that matches the method_data.
        Otherwise create a new child node.
        """
        return self.children.setdefault(method_data, ProfileNode(method_data))

    def jsonable(self):
        """
        Return Serializable data for json.
        """
        return [self.method, self.call_count, self.non_call_count,
                [x for x in self.children.values() if not x.ignore ]]

class ThreadProfiler(object):
    def __init__(self, profile_id, sample_period=0.1, duration=300,
            profile_agent_code=False):
        self._profiler_thread = threading.Thread(target=self._profiler_loop,
                name='NR-Profiler-Thread')
        self._profiler_thread.setDaemon(True)
        self._profiler_shutdown = threading.Event()

        self.profile_id = profile_id
        self._sample_count = 0
        self.start_time = 0
        self.stop_time = 0
        self.call_trees = {'REQUEST': {}, 
                'AGENT': {}, 
                'BACKGROUND': {}, 
                'OTHER': {}, 
                }
        self.sample_period = sample_period
        self.duration = duration
        self.profile_agent_code = profile_agent_code
        self.node_list = []
        ProfileNode.node_count = 0 # Reset node count to zero

    def _profiler_loop(self):
        while True:
            if self._profiler_shutdown.isSet():
                return 
            self._profiler_shutdown.wait(self.sample_period)
            self._run_profiler()
            if (time.time() - self.start_time) >= self.duration:
                self.stop_profiling()

    def _get_call_tree_bucket(self, thr):
        if thr is None:  # Thread is not active
            return None
        # NR thread
        if thr.getName().startswith('NR-'):
            if self.profile_agent_code:
                return self.call_trees['AGENT']
            else:
                return None

        transaction = Transaction._lookup_transaction(thr)
        if transaction is None:
            return self.call_trees['OTHER']
        elif transaction.background_task:
            return self.call_trees['BACKGROUND']
        else:
            return self.call_trees['REQUEST']

    def _run_profiler(self):
        self._sample_count += 1
        stacks = collect_thread_stacks()
        for thread_id, stack_trace in stacks.items():
            thr = threading._active.get(thread_id)
            bucket = self._get_call_tree_bucket(thr)
            if bucket is None:  # Approprite bucket not found
                continue
            if thread_id not in bucket.keys():
                bucket[thread_id] = ProfileNode(stack_trace[0])
            self._update_call_tree(bucket[thread_id], stack_trace)

    def _update_call_tree(self, call_tree, stack_trace):
        if call_tree.method != stack_trace[0]:
            return
        node = call_tree
        node.call_count += 1
        for method_data in stack_trace[1:]:
            node = node.get_or_create_child(method_data)
            node.call_count += 1
    
    def start_profiling(self):
        self.start_time = time.time()
        self._profiler_thread.start()

    def stop_profiling(self, forced=False):
        self.stop_time = time.time()
        self._profiler_shutdown.set()
        if forced:
            self._profiler_thread.join(self.sample_period)

    def profile_data(self):
        if self._profiler_thread.isAlive():
            return None
        call_data = {}
        thread_count = 0
        self._prune_trees(NODE_LIMIT)
        for thread_type, call_tree in self.call_trees.items():
            if not call_tree.values():  # Skip empty buckets
                continue
            call_data[thread_type] = call_tree.values()
            thread_count += len(call_tree)
        json_data = simplejson.dumps(call_data, default=alt_serialize,
                ensure_ascii=True, encoding='Latin-1',
                namedtuple_as_object=False)
        encoded_data = base64.standard_b64encode(zlib.compress(json_data))
        profile = [[self.profile_id, self.start_time*1000, self.stop_time*1000,
            self._sample_count, encoded_data, thread_count, 0]]
        return profile

    def _prune_trees(self, limit):
        if ProfileNode.node_count < limit:
            return
        for call_trees in self.call_trees.values():
            for call_tree in call_trees.values():
                self._node_to_list(call_tree)
        self.node_list.sort(key=lambda x: x.call_count)
        for node in self.node_list[limit:]:
            node.ignore = True

    def _node_to_list(self, node):
        if not node:
            return 
        self.node_list.append(node)
        for child_node in node.children.values():
            self._node_to_list(child_node)

def collect_thread_stacks():
    stack_traces = {}
    for thread_id, frame in sys._current_frames().items():
        stack_traces[thread_id] = []
        while frame:
            f = frame.f_code
            stack_traces[thread_id].append(_MethodData(f.co_filename,
                f.co_name, f.co_firstlineno))
            frame = frame.f_back
        stack_traces[thread_id].reverse()
    return stack_traces

def alt_serialize(data):
    """
    Alternate serializer for the ProfileNode object. Used by the json.dumps
    """
    if isinstance(data, ProfileNode):
        return data.jsonable()
    else:
        return data

def fib(n):
    if n < 2:
        return n
    return fib(n-1) + fib(n-2)

if __name__ == "__main__":
    t = ThreadProfiler(-1, 0.1, 1, profile_agent_code=True)
    t.start_profiling()
    #fib(35)
    import time
    time.sleep(1.1)
    #print t.profile_data()
    #print simplejson.dumps(t.profile_data())
    #t.prune_trees()
    #print t.node_list
    print zlib.decompress(base64.standard_b64decode(t.profile_data()[0][4]))
    #print ProfileNode.node_count