#!/usr/bin/env python3

## Overview

# ###
# This ROS2 script is designed to control a robot's docking behavior with a rack. 
# It utilizes odometry data, ultrasonic sensor readings, and provides docking control through a custom service. 
# The script handles both linear and angular motion to achieve docking alignment and execution.
# ###

# Import necessary ROS2 packages and message types
import os
import time
import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from geometry_msgs.msg import Twist
from sensor_msgs.msg import Range
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from tf_transformations import euler_from_quaternion
from ebot_docking.srv import DockSw  # Import custom service message
import math
from threading import Thread
from linkattacher_msgs.srv import AttachLink , DetachLink
from sensor_msgs.msg import Imu
from rclpy.time import Time
from std_msgs.msg import Bool
rclpy.init()
global robot_pose
global ultrasonic_value
ultrasonic_value = [0.0, 0.0]
robot_pose = [0.0, 0.0, 0.0,0.0]
class pid():
    def __init__(self):
        self.angleKp = 0.04
        self.linearKp = 0.5
        self.error = 0
        self.lastError = 0
        self.odomLinear = 0.5
        self.ultraKp=0.6
    def UltraOrientation(self):
        global ultrasonic_value
        error = ultrasonic_value[0] - ultrasonic_value[1]
        output = self.ultraKp * error
        # if abs(error)<5:
        #     output = 0.0 
        print("usrleft_value Left:",ultrasonic_value[0]," usrright_value Right:",ultrasonic_value[1]," error:",error," output:",output)
        return output
def main():
    ultraDockingNode = Node('ultra_docking_node')
    print("Docking node started")
    executor = rclpy.executors.MultiThreadedExecutor(1)
    executor.add_node(ultraDockingNode)
    executor_thread = Thread(target=executor.spin, daemon=True, args=())
    executor_thread.start()
    def ultrasonic_rl_callback(msg):
            global ultrasonic_value
            ultrasonic_value[0] = round(msg.range,2)

    def ultrasonic_rr_callback(msg):
        global ultrasonic_value
        ultrasonic_value[1] = round(msg.range,2)
    ultraDockingNode.ultrasonic_rl_sub = ultraDockingNode.create_subscription(Range, '/ultrasonic_rl/scan', ultrasonic_rl_callback, 10)
    ultraDockingNode.ultrasonic_rl_sub
    ultraDockingNode.ultrasonic_rr_sub = ultraDockingNode.create_subscription(Range, '/ultrasonic_rr/scan', ultrasonic_rr_callback, 10)
    ultraDockingNode.ultrasonic_rr_sub
    def moveBot(linearSpeedX,angularSpeed):
        ultraDockingNode.speedPub = ultraDockingNode.create_publisher(Twist, '/cmd_vel', 30)
        twist = Twist()
        twist.linear.x = linearSpeedX
        twist.angular.z = angularSpeed
        ultraDockingNode.speedPub.publish(twist)
    def UltraOrientation():
        global ultrasonic_value
        reached = False
        ultrasonicPid = pid()
        linearValue = -0.05
        while (reached == False):
            angularValue = ultrasonicPid.UltraOrientation()
            moveBot(linearValue,angularValue)
            avgUltraSonic = (ultrasonic_value[0]+ultrasonic_value[1])/2
            if avgUltraSonic <0.14:
                reached = True
            time.sleep(0.1)
    UltraOrientation()
    ultraDockingNode.destroy_node()
    rclpy.shutdown()
    exit(0)
if __name__ == '__main__':
    main()
