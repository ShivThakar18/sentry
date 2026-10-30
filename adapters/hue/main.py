import asyncio                      # run async code using an event loop
import os                           # access to environment variables

import httpx                        # HTTP client used to connect with Hue Bridge API
from dotenv import load_dotenv      # loads environment variables from a .env, required as our Hue IP and Key are stored there

async def main():
    
    load_dotenv()           # loads variables from .env files into this environment
                            # this allows us to keep sensitive information safe and out of our source code
    
    BRIDGE_IP = os.getenv("HUE_BRIDGE_IP")          # load Hue Bridge IP Address environment variable
    APP_KEY = os.getenv("HUE_APP_KEY")              # load Hue Application Key environment variable
    
    if not BRIDGE_IP or not APP_KEY:
        raise ValueError("Mising Hue Configuration in .env")    # throws an error if either Hue IP or Key are missing

    url = f"https://{BRIDGE_IP}/clip/v2/resource/light"         # construct the URL for the Hue API v2 light endpoints
                                                                # this endpoint returns information about all lights connected to the bridge
    
    
    # HTTP headers contain additional information sent with the request
    # Hue Bridge requires the application key to authenticate API requests
    headers = {
        "hue-application-key": APP_KEY
    }

    # Create an async HTTP client to communicate with the Hue Bridge
    async with httpx.AsyncClient(       # opens HTTP client and closes it automatically when done
        verify=False,                   # disables SSL certificate verification ebcause the Hue Bridge uses a certificate that is not trusted by default
        timeout=10.0,                   # times out after 10 seconds,  prevents the request from wiating indefinitely if the bridge does not respond
        trust_env=False                 # prevents system environment settings from interfering 
    ) as client:
        response = await client.get(url,headers=headers)        # pauses this coroutine until the HTTP request completes without blocking the entire asyncio event loop
                                                                # headers include app key 

        response.raise_for_status()         # check if HTTP request was successful

        lights = response.json().get("data",[])             # convert JSON object to Python Dictionary
                                                            # returns JSON object containing the data field that holds a list of light objects

        print(f'[INFO] Found {len(lights)} Hue Lights\n')   # print num of lights found

        for light in lights:        # iterate through lights list 

            light_id = light["id"]      # get ID assigned to this light , can be used to identify light in MQTT

            on = light.get("on",{}).get("on")   # retrieve the light's current power state (TRUE / FALSE)
                                                # Hue API stores - "on": {"on":true}
                                                # .get() safetly handles missing fields

            brightness=light.get("dimming",{}).get("brightness")    # retrieve the light's current brightness level
                                                                    # Hue API stores - "dimming": {"brightness": 75.0}
                                                                    # Brightness is represented as a percentage
                                                                    # Returns None, if not supported

            print(f"[INFO] Device Found: [light_id: \"{light_id}\", on: \"{on}\", brightness: \"{brightness}\"]")  # print data in the form of a debug log
            print("-"*30)


if __name__ == "__main__":
    asyncio.run(main())     # Start the asyncio event loop and execute the main() coroutine
                            # the event manages asynchronous operations such as HTTP requests 