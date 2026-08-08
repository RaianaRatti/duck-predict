from dotenv import load_dotenv
import os

load_dotenv()

# NOTE: Single representative lat/lon for CAISO-territory weather (see phase_1.3.md).
# NOTE: This point because it is Sacramento, it sits in Central Valley solar corridor near NP15, one of CAISO's curtailment-reporting zones
# NOTE: This is a simplification. CAISO spans a much larger area
WEATHER_LAT = float(os.getenv("WEATHER_LAT", "38.58"))
WEATHER_LON = float(os.getenv("WEATHER_LON", "-121.49"))