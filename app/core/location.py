import httpx
from typing import Optional, Tuple
from app.core.config import settings


class LocationService:
    """Location service using OpenStreetMap Nominatim for reverse geocoding."""

    def __init__(self):
        # Nominatim requires a User-Agent
        self.headers = {
            "User-Agent": f"{settings.APP_NAME}/1.0 (contact@flame.app)"
        }
        self.base_url = "https://nominatim.openstreetmap.org"

    async def reverse_geocode(
        self, latitude: float, longitude: float
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Get city, state, and country from coordinates.
        Returns: (city, state, country)
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/reverse",
                    params={
                        "lat": latitude,
                        "lon": longitude,
                        "format": "json",
                        "addressdetails": 1,
                        "zoom": 10,  # City level
                    },
                    headers=self.headers,
                    timeout=10.0,
                )

                if response.status_code != 200:
                    return None, None, None

                data = response.json()
                address = data.get("address", {})

                # Extract city (try multiple fields)
                city = (
                    address.get("city")
                    or address.get("town")
                    or address.get("village")
                    or address.get("municipality")
                    or address.get("county")
                )

                # Extract state/region
                state = address.get("state") or address.get("region")

                # Extract country
                country = address.get("country")

                return city, state, country

        except Exception as e:
            print(f"Geocoding error: {e}")
            return None, None, None

    async def get_location_string(self, latitude: float, longitude: float) -> Optional[str]:
        """Get a formatted location string like 'New York, NY'."""
        city, state, country = await self.reverse_geocode(latitude, longitude)

        if city and state:
            return f"{city}, {state}"
        elif city:
            return city
        elif state and country:
            return f"{state}, {country}"
        elif country:
            return country

        return None


# Global location service instance
location_service = LocationService()
