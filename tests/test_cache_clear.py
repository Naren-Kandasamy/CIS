import langchain_core.callbacks.manager
import atexit

exec1 = langchain_core.callbacks.manager._executor()
exec1.shutdown(wait=False)

try:
    exec2 = langchain_core.callbacks.manager._executor()
    exec2.submit(lambda: 1)
except RuntimeError as e:
    print(f"Error without clearing cache: {e}")

langchain_core.callbacks.manager._executor.cache_clear()
exec3 = langchain_core.callbacks.manager._executor()
print(f"After clearing cache, executor is different: {exec3 is not exec1}")
print("Submitting to new executor...")
f = exec3.submit(lambda: 42)
print(f"Result: {f.result()}")
