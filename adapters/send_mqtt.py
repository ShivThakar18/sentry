import aiomqtt
import json 
import argparse

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

def buildJson():
    
    built = {} 
    
    return built 

def main(): 
    
    parser.add_argument("on",type = bool,default=None)
    parser.add_argument("brightness",type = (int,float),default=None)
    parser.add_argument("color_xy",type=[float,float],default=None)
    parser.add_argument("color_temp_k",type=[int],default=None)
    
    args = parser.parser_args()
    
    on_off = args[1]
    brightness = args[2]
    color_xy = args[3]
    color_temp_k = args[4]
    
   
    for _ in range(args.count):
        print(f"Hello {args.name}")
    if args.verbose:
        print("done")
    
    return 



if __name__ == "__main__":
    main()
