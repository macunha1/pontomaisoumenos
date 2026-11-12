"""Process-local transport; SQL leases own durability and restart recovery."""

from dramatiq.brokers.stub import StubBroker
from dramatiq.common import current_millis, dq_name
from dramatiq.message import Message


class MemoryBroker(StubBroker):
    """Use Dramatiq's memory queues while preserving delayed retry metadata."""

    def enqueue(self, message: Message, *, delay: int | None = None) -> Message:
        # StubBroker replaces all options on delayed delivery, including the
        # retry counter. Preserve them so the actor's retry bound still applies.
        if delay is not None:
            message = message.copy(
                queue_name=dq_name(message.queue_name),
                options={**message.options, "eta": current_millis() + delay},
            )
        return super().enqueue(message)
