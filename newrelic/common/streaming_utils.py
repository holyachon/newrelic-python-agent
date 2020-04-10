import collections
import threading

try:
    from newrelic.core.infinite_tracing_pb2 import AttributeValue
except:
    AttributeValue = None


class StreamBuffer(object):

    def __init__(self, maxlen):
        self._queue = collections.deque(maxlen=maxlen)
        self._notify = StreamBuffer.condition()
        self._shutdown = False
        self._seen = 0
        self._dropped = 0

    @staticmethod
    def condition(*args, **kwargs):
        return threading.Condition(*args, **kwargs)

    def shutdown(self):
        with self._notify:
            self._shutdown = True
            self._notify.notify_all()

    def put(self, item):
        with self._notify:
            if self._shutdown:
                return

            self._seen += 1

            # NOTE: dropped can be over-counted as the queue approaches
            # capacity while data is still being transmitted.
            #
            # This is because the length of the queue can be changing as it's
            # being measured.
            if len(self._queue) >= self._queue.maxlen:
                self._dropped += 1

            self._queue.append(item)
            self._notify.notify_all()

    def stats(self):
        with self._notify:
            seen, dropped = self._seen, self._dropped
            self._seen, self._dropped = 0, 0

        return seen, dropped

    def __next__(self):
        while True:
            if self._shutdown:
                raise StopIteration

            try:
                return self._queue.popleft()
            except IndexError:
                pass

            with self._notify:
                if not self._shutdown and not self._queue:
                    self._notify.wait()

    next = __next__

    def __iter__(self):
        return self


class SpanProtoAttrs(dict):
    def __init__(self, *args, **kwargs):
        super(SpanProtoAttrs, self).__init__()
        if args:
            arg = args[0]
            if len(args) > 1:
                raise TypeError(
                        "SpanProtoAttrs expected at most 1 argument, got %d",
                        len(args))
            elif hasattr(arg, 'keys'):
                for k in arg:
                    self[k] = arg[k]
            else:
                for k, v in arg:
                    self[k] = v

        for k in kwargs:
            self[k] = kwargs[k]

    def __setitem__(self, key, value):
        super(SpanProtoAttrs, self).__setitem__(key,
                SpanProtoAttrs.get_attribute_value(value))

    def copy(self):
        copy = SpanProtoAttrs()
        copy.update(self)
        return copy

    @staticmethod
    def get_attribute_value(value):
        if isinstance(value, bool):
            return AttributeValue(bool_value=value)
        elif isinstance(value, float):
            return AttributeValue(double_value=value)
        elif isinstance(value, int):
            return AttributeValue(int_value=value)
        else:
            return AttributeValue(string_value=str(value))
