# Patch the crewai 1.14 cache_breakpoint bug BEFORE any submodule imports crewai.
import crewai.llms.cache as _crewai_cache
_crewai_cache.mark_cache_breakpoint = lambda msg: msg
