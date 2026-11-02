import json 
import argparse
from dotenv import load_dotenv
import os
import paho.mqtt.publish as publish

def publish_command(command):
    
    load_dotenv(dotenv_path="hue/.env")
    
    MQTT_HOST = os.getenv("MQTT_HOST","127.0.0.1")                 
    MQTT_PORT = int(os.getenv("MQTT_PORT","1883")) 
    
    
    device_id = "<insert-id>" # i will hardcode later
    
    MQTT_TOPIC = f"home/adapter/hue/{device_id}/set"

    publish.single(
        MQTT_TOPIC,
        payload=json.dumps(command),
        qos=1,
        hostname=MQTT_HOST,
        port=MQTT_PORT,
    )

    

def str_to_bool(s):
    s = s.lower()
    if s in ("true","1","on"):
        return True
    elif s in ("false","0","off"):
        return False

def buildJson(data):
    
    built = {} 
    fields = ["on","brightness","color_xy", "color_temp_k"]
    i = 0
    for d in data: 
        if d is None:
            continue
        if type(d) is list:
            built[fields[i]] = {
                    "x":d[0],
                    "y":d[1]
            }
        else:
            built[fields[i]] = d
        i+=1
        
    print(built)

    '''
    {
        "on": true, 
        "brightness": 40,
        "color_xy": {
            "x":0.17, 
            "y":0.07
            
        },
        "color_temp_k": 3000
    }
    '''
    
    return built 

def main(): 
    parser = argparse.ArgumentParser("Enter inputs")
    parser.add_argument("--on",type=str_to_bool,default=None)
    parser.add_argument("--brightness",type =float,default=None)
    parser.add_argument("--color_xy", type=float, nargs=2, metavar=("X", "Y"))
    parser.add_argument("--color_temp",type=int,default=None)
    
    args = parser.parse_args()
    
    
    
    data = [args.on, args.brightness, args.color_xy,args.color_temp]
  
    if data[2] and data[3]: 
        print("you cant change color temp and color at the same time")
        return
    
    buildJson(data)


if __name__ == "__main__":
    main()
