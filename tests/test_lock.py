import asyncio
from collections import OrderedDict

_locks = OrderedDict()

def get_lock(key):
    if key in _locks:
        return _locks[key]
    l = asyncio.Lock()
    _locks[key] = l
    return l

async def f1():
    lock = get_lock("A")
    async with lock:
        pass

async def f2():
    lock = get_lock("A")
    async with lock:
        pass

asyncio.run(f1())
asyncio.run(f2())
