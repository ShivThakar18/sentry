import json 
import argparse
from dotenv import load_dotenv
import os
import paho.mqtt.publish as publish


def list_devices(args):
    
    return

def status(args):
    
    return 

def watch(args): 
    
    return

def set_pub(args):
    
    data = [args.on,args.brightness,args.color_xy,args.color_temp]
    
    payload = {} 
    fields = ["on","brightness","color_xy", "color_temp_k"]
    
    i = 0 
    for d in data: 
        if d is None:
            i+=1
            continue
        if type(d) is list:
            payload[fields[i]] = {
                    "x":d[0],
                    "y":d[1]
            }
        else:
            payload[fields[i]] = d
        i+=1
    print(data)
    print(payload)
    
    load_dotenv(dotenv_path="hue/.env")
    
    MQTT_HOST = os.getenv("MQTT_HOST","127.0.0.1")                 
    MQTT_PORT = int(os.getenv("MQTT_PORT","1883")) 
    
    
    device_id = "<insert-id>" # i will hardcode later
    
    MQTT_TOPIC = f"home/adapter/hue/{device_id}/set"

    publish.single(
        MQTT_TOPIC,
        payload=json.dumps(payload),
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

def main(): 
    
    parser = argparse.ArgumentParser("Dev/Debug MQTT Tool. Publishes set directly")
    sub = parser.add_subparsers(dest="command", required = True)
    
    p = sub.add_parser("set")
    #p.add_argument("device")
    p.add_argument("--on",type=str_to_bool,default=None)
    p.add_argument("--brightness",type =float,default=None)
    p.add_argument("--color_xy", type=float, nargs=2, metavar=("X", "Y"))
    p.add_argument("--color_temp",type=int,default=None)
    p.set_defaults(func=set_pub)
    
    p = sub.add_parser("watch")
    p.add_argument("pattern",nargs="?",default="home/#")
    p.set_defaults(func=watch)
    
    p = sub.add_parser("list")
    p.add_argument("--wait",type=float,default=1.0)
    p.set_defaults(func=list_devices)
    
    p = sub.add_parser("status")
    p.add_argument("--wait", type=float, default=1.0)
    p.set_defaults(func=status)
    
    args = parser.parse_args()
    args.func(args)
    
    

if __name__ == "__main__":
    main()
