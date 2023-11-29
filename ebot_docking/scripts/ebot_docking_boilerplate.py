#!/usr/bin/env python3

## Overview

# ###
# This ROS2 script is designed to control a robot's docking behavior with a rack. 
# It utilizes odometry data, ultrasonic sensor readings, and provides docking control through a custom service. 
# The script handles both linear and angular motion to achieve docking alignment and execution.
# ###

# Import necessary ROS2 packages and message types
import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from geometry_msgs.msg import Twist
from sensor_msgs.msg import Range
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from tf_transformations import euler_from_quaternion
from ebot_docking.srv import DockSw  # Import custom service message
import math, statistics
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import Bool
import time
from threading import Thread
import numpy as np
from linkattacher_msgs.srv import AttachLink , DetachLink
from sensor_msgs.msg import Imu
rclpy.init()
global robot_pose
global ultrasonic_value
from std_msgs.msg import String
ultrasonic_value = [0.0, 0.0]
robot_pose = [0.0, 0.0, 0.0,0.0]


class pid():
    def __init__(self):
        self.angleKp = 0.012
        self.linearKp = 0.5
        self.error = 0
        self.lastError = 0
        self.odomLinear = 0.5
    def computeAngle(self ,setPoint, Input,X,Y):
        error = Input - setPoint                                         
        output = self.angleKp * error
        
        if(output > 0.6):
            output = 0.6
        elif(output < 0.2 and output > 0.0):
            output = 0.2
        elif(output < -0.6):
            output = -0.6
        elif(output > -0.2 and output < 0.0):
            output = -0.2         
        print("Input",Input,"setPoint",setPoint,"error",error,"output",output)
        return output*-1.0
    def computeLinear(self,InputY,setPointY):
        error = InputY - setPointY                                         
        output = self.linearKp * error  
        if output < 0.1:
            output = 0.1
        # print("InputY",InputY,"setPointY",setPointY,"error",error,"output",output)
        
        return output*-1.0    
    def odomComputeLinear(self,Input,Setpoint):
        error = Input - Setpoint                                         
        output = self.odomLinear * error  
        if output < 0.2:
            output = 0.2
        return output*-1.0
    # def computeLinear(self, Input ,setPoint):
    #     error = Input - setPoint                                          
    #     output = self.kp * error + self.kd * (error - self.lastError) + self.ki * (self.ki + error)
    #     self.lastError = error
    #     output = output + 1
    #     return output
# Define a class for your ROS2 node

class MyRobotDockingController(Node):

    def __init__(self):
        # Initialize the ROS2 node with a unique name
        super().__init__('my_robot_docking_controller')
        global robot_pose
        # Create a callback group for managing callbacks
        self.callback_group = ReentrantCallbackGroup()
        
        # Subscribe to odometry data for robot pose information
        

        # Subscribe to ultrasonic sensor data for distance measurements
        self.ultrasonic_rl_sub = self.create_subscription(Range, '/ultrasonic_rl/scan', self.ultrasonic_rl_callback, 10)
        # Add another one here
        self.ultrasonic_rr_sub = self.create_subscription(Range, '/ultrasonic_rr/scan', self.ultrasonic_rr_callback, 10)

        # Create a ROS2 service for controlling docking behavior, can add another custom service message
        self.dock_control_srv = self.create_service(DockSw, '/dock_control', self.dock_control_callback, callback_group=self.callback_group)
        self.isDocked = self.create_publisher(Bool, '/dockingSuccesfull', 10)
        self.speedPub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.workRack = self.create_publisher(String, '/pickup_Box', 10)
        self.link_attach_cli = self.create_client(AttachLink, '/ATTACH_LINK')
        self.lind_detached_cli = self.create_client(DetachLink, '/DETACH_LINK')
        while not self.link_attach_cli.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('Link attacher service not available, waiting again...')
        
        # Initialize all  flags and parameters here
        self.is_docking = False
        self.dock_aligned=False
        self.usrleft_value=0
        self.usrright_value=0
        self.turn=1
        self.speed=0.5
        self.targetX=0
        self.targetY=0
        self.targetYaw=0
        self.rackName = ""
        self.isAttach = False
        #         
        # 
        # 
        # 
        # 
        # 

        # Initialize a timer for the main control loop
        self.controller_timer = self.create_timer(0.1, self.controller_loop)

    def moveBot(self,linearSpeedX,angularSpeed):
        twist = Twist()
        twist.linear.x = linearSpeedX
        twist.angular.z = angularSpeed
        self.speedPub.publish(twist)
    # Callback function for the left ultrasonic sensor
    def ultrasonic_rl_callback(self, msg):
        self.usrleft_value = msg.range

    def ultrasonic_rr_callback(self, msg):
        self.usrright_value = msg.range
    # Callback function for the right ultrasonic sensor
    #
    #
    def attachRack(self,rackName):
            req = AttachLink.Request()
            req.model1_name =  'ebot'     
            req.link1_name  = 'ebot_base_link'       
            req.model2_name =  rackName       
            req.link2_name  = 'link' 
            self.link_attach_cli.call_async(req)   
    def detachRack(self,rackName):
            req = DetachLink.Request()
            req.model1_name =  'ebot'     
            req.link1_name  = 'ebot_base_link'       
            req.model2_name =  rackName       
            req.link2_name  = 'link' 
            self.lind_detached_cli.call_async(req)
    def is_at_goal(self,current_x, current_y, goal_x, goal_y, tolerance=0.04):
        
        distance = ((current_x - goal_x)**2 + (current_y - goal_y)**2)**0.5
        return distance <= tolerance

    def getRemaningDistance(self, current_x, current_y, goal_x, goal_y):
        distance = ((abs(current_x) - abs(goal_x))**2 + (abs(current_y) - abs(goal_y))**2)**0.5
        return distance
    # Utility function to normalize angles within the range of -π to π (OPTIONAL)
    def normalize_angle(self,angle):
        """Normalizes an angle to the range [-π, π].
    
        Args:
            angle: A float representing the angle in radians.

        Returns:
            A float representing the normalized angle in radians.
        """
        global robot_pose
        if self.targetYaw == 0.0:
            return angle

        if angle<0:
            angle = angle + 360
        return angle
    
    # Main control loop for managing docking behavior
    def is_bot_at_goal_position(self,bot_x, bot_y, goal_x, goal_y, tolerance=3.0):
        """Checks if the bot is at the goal position.

        Args:
            bot_x: The bot's current X position.
            bot_y: The bot's current Y position.
            goal_x: The goal X position.
            goal_y: The goal Y position.
            tolerance: The tolerance value.

        Returns:
            A Boolean value indicating whether the bot is at the goal position.
        """

        x_diff = abs(bot_x - goal_x)
        y_diff = abs(bot_y - goal_y)
        print("x_diff",x_diff,"y_diff",y_diff)
        return x_diff <= tolerance and y_diff <= tolerance
    def calculate_distance(self,x1, y1, x2, y2):
        return math.sqrt((x2 - x1)**2 + (y2 - y1)**2)   
    def is_robot_within_tolerance(self,current_x, current_y, current_orientation, goal_x, goal_y, goal_orientation,
                                x_tolerance=0.3, y_tolerance=0.3, orientation_tolerance=10):
        """
        Check if the robot is within tolerance for X axis, Y axis, and Orientation.

        Parameters:
        - current_x: Current X axis position of the robot.
        - current_y: Current Y axis position of the robot.
        - current_orientation: Current orientation of the robot.
        - goal_x: Goal X axis position for the robot.
        - goal_y: Goal Y axis position for the robot.
        - goal_orientation: Goal orientation for the robot.
        - x_tolerance: Tolerance for the X axis (default is 3.0).
        - y_tolerance: Tolerance for the Y axis (default is 3.0).
        - orientation_tolerance: Tolerance for the orientation (default is 10).

        Returns:
        - True if the robot is within tolerance, False otherwise.
        """
        x_difference = abs(goal_x)-abs(current_x)
        y_difference = abs(goal_y)-abs(current_y)
        orientation_difference = abs(goal_orientation) - abs(current_orientation)
        print("x_difference",x_difference,"y_difference",y_difference,"orientation_difference",orientation_difference)
        x_within_tolerance = x_difference <= x_tolerance
        y_within_tolerance = y_difference <= y_tolerance
        orientation_within_tolerance = orientation_difference <= orientation_tolerance

        return x_within_tolerance and y_within_tolerance and orientation_within_tolerance
    
    def getWhichIsGreater(self,currentX,currentY):
        goalX = self.targetX
        goalY = self.targetY
        AbsdifferenceX = abs(abs(currentX) - abs(goalX))
        AbsdifferenceY = abs(abs(currentY) - abs(goalY))
        # print("AbsdifferenceX",AbsdifferenceX,"AbsdifferenceY",AbsdifferenceY)
        if AbsdifferenceX > AbsdifferenceY:
            # print("X is greater")
            return 0
        else:
            # print("Y is greater")
            return 1
    def distanceSingle(self,x1, x2):
        return math.sqrt((x1 - x2) ** 2)*1.0
    def UltralinearDockingprocess(self,leftUltraSonic,rightUltraSonic):
        avgUltraSonic = (leftUltraSonic+rightUltraSonic)/2
        reached = False
        if avgUltraSonic <0.1:
            reached = True
        linearPid = pid()
        return linearPid.computeLinear(avgUltraSonic,0.1),reached
    def UltraLinearDocking(self):
        reached = False    
        while (reached == False):
            X,reached=self.UltralinearDockingprocess(ultrasonic_value[0],ultrasonic_value[1]) 
            print("usrleft_value:",ultrasonic_value[0]," usrright_value:",ultrasonic_value[1]," Reached:",reached)
            self.moveBot(X,0.0)
    def odomLinearDockingprocess(self,InputDistance,Setpoint=0.1):
        odomlinearPid = pid()
        reached =False
        if InputDistance <0.1:
            reached = True
            return 0.0
        return odomlinearPid.odomComputeLinear(InputDistance,Setpoint)
    def odomLinearDocking(self):
        global robot_pose
        reachedExtra = False    
        X1 =self.getWhichIsGreater(robot_pose[0],robot_pose[1])
        while (reachedExtra == False):
            if X1 == 0:
                distance=self.distanceSingle(self.targetX,robot_pose[0])
                if distance < 0.15:
                    reachedExtra = True
                print("X: target",self.targetX,"current",robot_pose[0],"distance",distance)
            elif X1 == 1:
                distance=self.distanceSingle(self.targetY,robot_pose[1])
                if distance < 0.15:
                    reachedExtra = True
                print("Y: target",self.targetY,"current",robot_pose[1],"distance",distance)
            # distance=self.calculate_distance(robot_pose[0],robot_pose[1],self.targetX,self.targetY)
            speed=self.odomLinearDockingprocess(distance)
            self.moveBot(speed,0.0)
            # print("X",distance," Reached:",reached)
    def AngularDocking(self):   
        yaw = False
        botPid = pid()
        while (yaw == False):
            angle=botPid.computeAngle(int(self.normalize_angle(self.targetYaw)),int(self.normalize_angle(robot_pose[2])),robot_pose[0],robot_pose[1])
            self.moveBot(0.0,angle)
            yaw = True if(int(self.normalize_angle(self.targetYaw)) == int(self.normalize_angle(robot_pose[2]))) else False
            time.sleep(0.01)

    
    def controller_loop(self):

        # The controller loop manages the robot's linear and angular motion 
        # control to achieve docking alignment and execution
        
        # print("controller loop")
        def odometry_callback(msg):
        # Extract and update robot pose information from odometry message
            global robot_pose
            robot_pose[0] = round(msg.pose.pose.position.x,2)
            robot_pose[1] = round(msg.pose.pose.position.y,2)
            robot_pose[3] = round(msg.pose.pose.position.z,2)
        def imu_callback(msg):
            global robot_pose
            quaternion_array = msg.orientation
            orientation_list = [quaternion_array.x, quaternion_array.y, quaternion_array.z, quaternion_array.w]
            _, _, yaw = euler_from_quaternion(orientation_list)
            yaw = math.degrees(yaw)
            robot_pose[2] = yaw
            # print("robot_pose",robot_pose)
        def ultrasonic_rl_callback(msg):
            global ultrasonic_value
            ultrasonic_value[0] = round(msg.range,2)

        def ultrasonic_rr_callback(msg):
            global ultrasonic_value
            ultrasonic_value[1] = round(msg.range,2)
            # print("ultrasonic_value",ultrasonic_value)
        if self.is_docking:
            # ...
            # Implement control logic here for linear and angular motion
            # For example P-controller is enough, what is P-controller go check it out !
            # ...
            global robot_pose
            global ultrasonic_value
            dockingNode = Node("GlobalNodeDocking")
            
            executor = MultiThreadedExecutor(3)
            executor.add_node(dockingNode)
            executor_thread = Thread(target=executor.spin, daemon=True, args=())
            executor_thread.start()
            dockingNode.odom_sub = dockingNode.create_subscription(Odometry, '/odom', odometry_callback, 10)
            dockingNode.odom_sub
            dockingNode.imu_sub = dockingNode.create_subscription(Imu, '/imu', imu_callback, 10)
            dockingNode.imu_sub
            dockingNode.ultrasonic_rl_sub = dockingNode.create_subscription(Range, '/ultrasonic_rl/scan', ultrasonic_rl_callback, 10)
            dockingNode.ultrasonic_rl_sub
            dockingNode.ultrasonic_rr_sub = dockingNode.create_subscription(Range, '/ultrasonic_rr/scan', ultrasonic_rr_callback, 10)
            dockingNode.ultrasonic_rr_sub
            time.sleep(0.5)

            self.AngularDocking()
            for i in range(5):
                self.moveBot(0.0,0.0)     
            #orientation done
            if not self.rackName=="initalPose":
                if self.isAttach:
                    self.UltraLinearDocking()
                    for i in range(5):
                        self.moveBot(0.0,0.0)
                    time.sleep(0.5)
                else:
                    self.odomLinearDocking()
                    for i in range(5):
                        self.moveBot(0.0,0.0)
                    time.sleep(0.5)
                #linear done
                self.AngularDocking()
                for i in range(5):
                    self.moveBot(0.0,0.0)
                #orientation done
                print("is_robot_within_tolerance",self.is_robot_within_tolerance(robot_pose[0], robot_pose[1], robot_pose[2],self.targetX, self.targetY, self.targetYaw))
                if self.isAttach:
                    self.attachRack(self.rackName)
                else :
                    self.detachRack(self.rackName)
                    boxID = String()
                    tempBoxID = self.rackName
                    boxID.data =  tempBoxID.join(tempBoxID)
                    
                    time.sleep(0.5)
                    for i in range(5):
                            self.moveBot(1.0,0.0)
                            self.workRack.publish(boxID)
                    time.sleep(0.6)
                    for i in range(5):
                        self.moveBot(0.0,0.0)
                        self.workRack.publish(boxID)
            self.is_docking = False
            self.dock_aligned=True
            ## docking and orientation done
            dockingNode.destroy_node()
            
            pass
    
    # Callback function for the DockControl service
    def dock_control_callback(self, request, response):
        # Extract desired docking parameters from the service request
        #
        #
        self.targetX = request.goal_x
        self.targetY = request.goal_y
        self.targetYaw = request.orientation
        self.rackName = request.rack_no
        self.isAttach = request.rack_attach
        # Reset flags and start the docking process
        #
        #
        for i in range(10):
            msg = Bool()
            msg.data = False
            self.isDocked.publish(msg)
        for i in range(5):
            self.moveBot(0.0,0.0)
        
        self.is_docking = True
        self.controller_loop()
        
        # Log a message indicating that docking has started
        self.get_logger().info("Docking started!")

        # Create a rate object to control the loop frequency
        rate = self.create_rate(2, self.get_clock())
        # Wait until the robot is aligned for docking
        while not self.dock_aligned:
            # self.get_logger().info("Waiting for alignment...")
            
            rate.sleep()

        # Set the service response indicating success
        response.success = True
        for i in range(10):
            msg = Bool()
            msg.data = True
            self.isDocked.publish(msg)
        
        response.message = "Docking control completed "
        print(request)
        return response

# Main function to initialize the ROS2 node and spin the executor
def main(args=None):
    

    my_robot_docking_controller = MyRobotDockingController()

    executor = MultiThreadedExecutor(2)
    executor.add_node(my_robot_docking_controller)
    executor_thread = Thread(target=executor.spin, daemon=True, args=())
    executor_thread.start()
    rclpy.spin(my_robot_docking_controller)
    my_robot_docking_controller.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()