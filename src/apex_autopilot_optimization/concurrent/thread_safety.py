"""Thread-safe wrappers for mutable objects."""

from __future__ import annotations

import threading
from typing import Any, Callable, Generic, Iterator, TypeVar

_T = TypeVar("_T")
_K = TypeVar("_K")
_V = TypeVar("_V")


class ThreadSafeWrapper(Generic[_T]):
    """Wraps any mutable object, serialising all attribute access through a re-entrant lock.

    Every method call or attribute read/write on the wrapped object is guarded by
    a single :class:`threading.RLock`, making the wrapper safe to share across
    threads.
    """

    def __init__(self, obj: _T) -> None:
        object.__setattr__(self, "_obj", obj)
        object.__setattr__(self, "_lock", threading.RLock())

    def __getattr__(self, name: str) -> Any:
        with object.__getattribute__(self, "_lock"):
            return getattr(object.__getattribute__(self, "_obj"), name)

    def __setattr__(self, name: str, value: Any) -> None:
        with object.__getattribute__(self, "_lock"):
            setattr(object.__getattribute__(self, "_obj"), name, value)

    def __delattr__(self, name: str) -> None:
        with object.__getattribute__(self, "_lock"):
            delattr(object.__getattribute__(self, "_obj"), name)


class ThreadSafeDict(Generic[_K, _V]):
    """A dict subclass that serialises all operations through a re-entrant lock."""

    def __init__(self, initial: dict[_K, _V] | None = None) -> None:
        self._data: dict[_K, _V] = dict(initial) if initial else {}
        self._lock = threading.RLock()

    def __getitem__(self, key: _K) -> _V:
        with self._lock:
            return self._data[key]

    def __setitem__(self, key: _K, value: _V) -> None:
        with self._lock:
            self._data[key] = value

    def __delitem__(self, key: _K) -> None:
        with self._lock:
            del self._data[key]

    def __contains__(self, key: object) -> bool:
        with self._lock:
            return key in self._data

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)

    def __iter__(self) -> Iterator[_K]:
        with self._lock:
            return iter(list(self._data.keys()))

    def get(self, key: _K, default: _V | None = None) -> _V | None:
        with self._lock:
            return self._data.get(key, default)

    def keys(self) -> list[_K]:
        with self._lock:
            return list(self._data.keys())

    def values(self) -> list[_V]:
        with self._lock:
            return list(self._data.values())

    def items(self) -> list[tuple[_K, _V]]:
        with self._lock:
            return list(self._data.items())

    def update(self, other: dict[_K, _V]) -> None:
        with self._lock:
            self._data.update(other)

    def pop(self, key: _K, default: Any = None) -> _V | None:
        with self._lock:
            return self._data.pop(key, default)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


class ThreadSafeList(Generic[_T]):
    """A list subclass that serialises all operations through a re-entrant lock."""

    def __init__(self, initial: list[_T] | None = None) -> None:
        self._data: list[_T] = list(initial) if initial else []
        self._lock = threading.RLock()

    def __getitem__(self, index: int | slice) -> _T | list[_T]:
        with self._lock:
            return self._data[index]

    def __setitem__(self, index: int, value: _T) -> None:
        with self._lock:
            self._data[index] = value

    def __delitem__(self, index: int) -> None:
        with self._lock:
            del self._data[index]

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)

    def __iter__(self) -> Iterator[_T]:
        with self._lock:
            return iter(list(self._data))

    def append(self, item: _T) -> None:
        with self._lock:
            self._data.append(item)

    def extend(self, items: list[_T]) -> None:
        with self._lock:
            self._data.extend(items)

    def pop(self, index: int = -1) -> _T:
        with self._lock:
            return self._data.pop(index)

    def insert(self, index: int, item: _T) -> None:
        with self._lock:
            self._data.insert(index, item)

    def remove(self, item: _T) -> None:
        with self._lock:
            self._data.remove(item)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def count(self, item: _T) -> int:
        with self._lock:
            return self._data.count(item)

    def index(self, item: _T) -> int:
        with self._lock:
            return self._data.index(item)
