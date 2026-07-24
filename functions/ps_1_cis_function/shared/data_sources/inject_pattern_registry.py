from typing import Callable, Any
import logging

logger = logging.getLogger(__name__)

class PatternInjectorRegistry:
    """
    Central registry for all deterministic pattern injection generators.
    Ensures deterministic execution and logs the patterns planted (Ground Truth tagging).
    """
    def __init__(self):
        self._generators = {}
        self._execution_log = []

    def register(self, pattern_name: str, func: Callable):
        self._generators[pattern_name] = func

    def run(self, pattern_name: str, **params) -> Any:
        if pattern_name not in self._generators:
            raise ValueError(f"Pattern {pattern_name} not registered in PatternInjectorRegistry")
        
        logger.info(f"Injecting signature: {pattern_name} with params: {params}")
        
        result = self._generators[pattern_name](**params)
        
        self._execution_log.append({
            "pattern_name": pattern_name,
            "params": params,
            "status": "success"
        })
        
        return result

    def get_log(self) -> list[dict]:
        return self._execution_log

# Global registry instance
pattern_registry = PatternInjectorRegistry()
