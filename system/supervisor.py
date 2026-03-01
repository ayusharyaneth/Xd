import asyncio
import traceback
from utils.logger import log

class TaskSupervisor:
    """
    Prevents silent failures by wrapping tasks in a supervised loop.
    """
    @staticmethod
    async def create_task(coro, name="UnknownTask"):
        try:
            await coro
        except asyncio.CancelledError:
            log.info(f"Task {name} cancelled.")
        except Exception as e:
            log.critical(f"Task {name} crashed: {e}")
            log.error(traceback.format_exc())
            # Optional: Add restart logic here
