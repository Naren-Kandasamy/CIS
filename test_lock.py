import asyncio

_locks = {}

def get_lock(key):
    if key in _locks:
        return _locks[key]
    lock = asyncio.Lock()
    _locks[key] = lock
    return lock

async def main1():
    lock = get_lock("my_lock")
    async with lock:
        print("Acquired in main1")

async def main2():
    lock = get_lock("my_lock")
    async with lock:
        print("Acquired in main2")

asyncio.run(main1())
try:
    asyncio.run(main2())
except Exception as e:
    print("Error in main2:", type(e), e)

