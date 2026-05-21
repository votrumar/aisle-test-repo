import aiohttp


async def fetch_status(url: str, *, timeout_seconds: float = 5.0) -> int:
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as response:
            return response.status
