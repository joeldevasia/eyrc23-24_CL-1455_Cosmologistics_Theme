#!/usr/bin/env python3

## Overview

# ###
# This ROS2 script is designed to control a robot's docking behavior with a rack. 
# It utilizes odometry data, ultrasonic sensor readings, and provides docking control through a custom service. 
# The script handles both linear and angular motion to achieve docking alignment and execution.
# ###

# Import necessary ROS2 packages and message types
import os

import yaml
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
from std_msgs.msg import String
rclpy.init()
global robot_pose
global ultrasonic_value
global aruco_name_list
global aruco_angle_list
global aruco_ap_list
aruco_name_list = []
aruco_angle_list = []
aruco_ap_list = []
ultrasonic_value = [0.0, 0.0]
robot_pose = [0.0, 0.0, 0.0,0.0]


class pid():
    def __init__(self):
        self.angleKp = 0.04
        self.linearKp = 0.5
        self.error = 0
        self.lastError = 0
        self.odomLinear = 0.2
        self.ultraKp=0.08
    def computeAngle(self ,setPoint, Input,X,Y):
        error = Input - setPoint                                         
        output = self.angleKp * error
        
        if(output > 1.0):
            output = 1.0
        elif(output < 0.2 and output > 0.0):
            output = 0.2
        elif(output < -1.0):
            output = -1.0
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
        if output < 0.3:
            output = 0.3
        return output*-1.0
    def UltraOrientation(self,input,isLinear):
        global ultrasonic_value
        error = input
        output = self.ultraKp * error
        output = round(output,3)
        result = False
        if abs(round(error,3))<=0.3:
            result = True 
        mode=""
        if isLinear:
            mode="Linear"
        else:
            mode="Angular"
        print("mode",mode,"usrleft_value Left:",round(ultrasonic_value[0],1)," usrright_value Right:",round(ultrasonic_value[1],1)," error:",error," output:",output)
        return output*-1.0,result
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
        

      # Create a ROS2 service for controlling docking behavior, can add another custom service message
        self.dock_control_srv = self.create_service(DockSw, '/dock_control', self.dock_control_callback, callback_group=self.callback_group)
        self.speedPub = self.create_publisher(Twist, '/cmd_vel', 30)
        self.nav2speedPub = self.create_publisher(Twist, '/cmd_vel_nav', 30)
        
        # Initialize all  flags and parameters here
        self.is_docking = False
        self.dock_aligned=False
        self.usrleft_value=0
        self.usrright_value=0
        self.targetX=0
        self.targetY=0
        self.targetYaw=0
        self.rackName = ""
        self.isAttach = False
        self.globalnodeClock = self.get_clock()
        self.isRackDetach = False
        self.BoxId = None    
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
    # Callback function for the right ultrasonic sensor
    #
    #
    
            # rclpy.spin_until_future_complete(self, self.lind_detached_cli) 
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
    
    def calculate_distance(self,x1, y1, x2, y2):
        return math.sqrt((x2 - x1)**2 + (y2 - y1)**2)   
    def GlobalStopTime(self,StopSeconds):
        future_time = Time(seconds=self.globalnodeClock.now().nanoseconds / 1e9 + StopSeconds, clock_type=self.globalnodeClock.clock_type)
        self.globalnodeClock.sleep_until(future_time)
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
    
    def odomLinearDockingprocess(self,InputDistance,Setpoint=0.1):
        odomlinearPid = pid()
        if InputDistance <0.12:   
            return 0.0
        return odomlinearPid.odomComputeLinear(InputDistance,Setpoint)
    def Whichaxistomove(self):
        yaw = abs(self.targetYaw) 
        if yaw > 200.0:
            return 1
        elif yaw > 150.0:
            return 0
        elif yaw > 80.0:
            return 1
        else:
            return 0 
    def cameraYawConversion(self,yaw):
        if self.targetYaw >= 178.0 and self.targetYaw <= 182.0:
            return 180 - yaw

        if yaw>0:
            yaw =  360 - yaw
        return int(yaw)
    def is_yaw_within_tolerance(self,current_yaw, target_yaw, tolerance=5):
        # Calculate the difference between the yaw angles
        yaw_diff = abs(current_yaw - target_yaw)

        # Check if the difference is within the tolerance
        print("inside yaw ",yaw_diff)
        return yaw_diff <= tolerance
    def odomLinearDocking(self):
        global robot_pose
        reachedExtra = False    
        # X1 =self.getWhichIsGreater(robot_pose[0],robot_pose[1])
        X1 = self.Whichaxistomove()
        while (reachedExtra == False):
            if X1 == 0:
                distance=self.distanceSingle(self.targetX,robot_pose[0])
                if distance < 0.15:
                    reachedExtra = True
                print("X: target",self.targetX,"current",robot_pose[0],"distance",distance)
            else:
                distance=self.distanceSingle(self.targetY,robot_pose[1])
                if distance < 0.15:
                    reachedExtra = True
                print("Y: target",self.targetY,"current",robot_pose[1],"distance",distance)
            speed=self.odomLinearDockingprocess(distance)
            self.moveBot(speed,0.0)
            self.GlobalStopTime(0.1)
    def UltraOrientation(self):
        global ultrasonic_value
        reached = False
        ultrasonicPid = pid()
        
        while (reached == False):
        
            m = (ultrasonic_value[1] - ultrasonic_value[0])
            angularValue,reached = ultrasonicPid.UltraOrientation(m,False)
            print("m:",m)
            self.moveBot(0.0,angularValue)
            self.GlobalStopTime(0.1)
    def UltraOrientationLinear(self):
        global ultrasonic_value
        reached = False
        ultrasonicPid = pid()
        linearValue = -0.2
        while (reached == False):

            m = (ultrasonic_value[1] - ultrasonic_value[0])
            angularValue ,check = ultrasonicPid.UltraOrientation(m,True)

            self.moveBot(linearValue,angularValue)
            avgUltraSonic = (ultrasonic_value[0]+ultrasonic_value[1])/2
            if avgUltraSonic <18.0:
                reached = True
            self.GlobalStopTime(0.1)    
    def AngularDocking(self):   
        yaw = False
        botPid = pid()
        while (yaw == False):
            angle=botPid.computeAngle(int(self.normalize_angle(self.targetYaw)),int(self.normalize_angle(robot_pose[2])),robot_pose[0],robot_pose[1])
            self.moveBot(0.0,angle)
            yaw = True if(int(self.normalize_angle(self.targetYaw)) == int(self.normalize_angle(robot_pose[2]))) else False
            self.GlobalStopTime(0.1)
    def manualMoveBot(self):
        global robot_pose,aruco_name_list,aruco_angle_list,aruco_ap_list
        # value = input("Move Bot")
        target_rack = "obj_"+self.BoxId
        self.GlobalStopTime(1.0)
        rackIndex = self.find_string_in_list(target_rack,aruco_name_list)
        counter = 1
        
        # if value == "y":
        while rackIndex == -1:
            counter = counter + 1
            if counter > 100:
                self.moveBot(0.0,0.0)
                self.moveBot(0.0,0.0)
                return None
            rackIndex = self.find_string_in_list(target_rack,aruco_name_list)
            print("running manual mode")
            print("rackIndex",rackIndex)
            print("target_rack",target_rack)
            print("aruco_ap_list",aruco_ap_list)
            print("aruco_name_list",aruco_name_list)
            print("x",robot_pose[0],"y",robot_pose[1])
            # print("cameraYaw",cameraYaw)
            self.GlobalStopTime(0.1)
            self.moveBot(-0.05,0.0)
        self.moveBot(0.0,0.0)
        self.moveBot(0.0,0.0)
    def find_string_in_list(self,string, list):
        for index, item in enumerate(list):
            if item == string:
                return index
        return -1
    def cameraOrientation(self):
        global aruco_name_list,aruco_angle_list,aruco_ap_list
        self.manualMoveBot()
        botPid = pid()
        target_rack = "obj_"+self.BoxId   
        rackIndex = self.find_string_in_list(target_rack,aruco_name_list)
        targetYAw = int(self.normalize_angle(self.targetYaw))
        counter = 1
        while rackIndex == -1:
            counter = counter + 1
            rackIndex = self.find_string_in_list(target_rack,aruco_name_list)
            print("rackIndex",rackIndex)
            print("target_rack",target_rack)
            print("aruco_ap_list",aruco_ap_list)
            print("counter",counter)
            # print("cameraYaw",cameraYaw)
            self.GlobalStopTime(0.1)
            if counter >100:
                return None
                
        yaw = False
        while yaw == False:
            rackIndex = self.find_string_in_list(target_rack,aruco_name_list)
            cameraYaw = self.cameraYawConversion(aruco_angle_list[rackIndex])
            print("rackIndex",rackIndex)
            print("cameraYaw",cameraYaw)
            print("targetYaw",targetYAw)
            print("yaw Checker",yaw)
            angle=botPid.computeAngle(targetYAw,cameraYaw,robot_pose[0],robot_pose[1])
            self.moveBot(0.0,-angle)
            yaw = self.is_yaw_within_tolerance((cameraYaw),targetYAw)
            print("yaw Checker",yaw)
            self.GlobalStopTime(0.1)
        for i in range(5):
            self.moveBot(0.0,0.0)
        
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
            robot_pose[2] = round(yaw,2)
            # print("robot_pose",robot_pose)
        def ultrasonic_rl_callback(msg):
            global ultrasonic_value
            ultrasonic_value[0] = round(msg.range,3)
            ultrasonic_value[0] = ultrasonic_value[0]*100

        def ultrasonic_rr_callback(msg):
            global ultrasonic_value
            ultrasonic_value[1] = round(msg.range,3)
            ultrasonic_value[1] = ultrasonic_value[1]*100
            # print("ultrasonic_value",ultrasonic_value)
        def aruco_data_updater(msg):
            global aruco_name_list
            global aruco_angle_list
            global aruco_ap_list
            data = yaml.safe_load(msg.data)
            aruco_name_list = data.get("id")
            aruco_angle_list = data.get("angle")
            aruco_ap_list = data.get("ap")
        if self.is_docking:
            # ...
            # Implement control logic here for linear and angular motion
            # For example P-controller is enough, what is P-controller go check it out !
            # ...
            global robot_pose
            global ultrasonic_value
            dockingNode = Node("GlobalNodeDocking")
            callback_group = ReentrantCallbackGroup()
            docking_executor = MultiThreadedExecutor(1)
            docking_executor.add_node(dockingNode)
            executor_thread = Thread(target=docking_executor.spin, daemon=True, args=())
            executor_thread.start()
            dockingNode.odom_sub = dockingNode.create_subscription(Odometry, '/odom', odometry_callback, 10, callback_group=callback_group)
            dockingNode.imu_sub = dockingNode.create_subscription(Imu, '/imu', imu_callback, 10, callback_group=callback_group)
            dockingNode.ultrasonic_rl_sub = dockingNode.create_subscription(Range, '/ultrasonic_rl/scan', ultrasonic_rl_callback, 10, callback_group=callback_group)
            dockingNode.ultrasonic_rr_sub = dockingNode.create_subscription(Range, '/ultrasonic_rr/scan', ultrasonic_rr_callback, 10, callback_group=callback_group)
            dockingNode.aruco_data_subscriber = dockingNode.create_subscription(String, "/aruco_data", aruco_data_updater, 10, callback_group=callback_group)
            dockingNodeClock = dockingNode.get_clock()
            dockingNode.link_attach_cli = dockingNode.create_client(AttachLink, '/ATTACH_LINK')
            dockingNode.lind_detached_cli = dockingNode.create_client(DetachLink, '/DETACH_LINK')
            def StopTime(StopSeconds):
                future_time = Time(seconds=dockingNodeClock.now().nanoseconds / 1e9 + StopSeconds, clock_type=dockingNodeClock.clock_type)
                dockingNodeClock.sleep_until(future_time)  
            def stopBot(time,linearSpeedX=0.0,angularSpeed=0.0):
                for i in range(2):
                    self.moveBot(linearSpeedX,angularSpeed)   
                    StopTime(time)  
            def attachRack(rackName):
                
                req = AttachLink.Request()
                req.model1_name =  'ebot'     
                req.link1_name  = 'ebot_base_link'       
                req.model2_name =  rackName       
                req.link2_name  = 'link'
                dockingNode.future = dockingNode.link_attach_cli.call_async(req) 
                
                # rclpy.spin_until_future_complete(dockingNode, dockingNode.future,docking_executor,1.0) 
                while dockingNode.future is None :
                    stopBot(0.1)
                # print("RelayNode.future.result()",RelayNode.future)
                print("Rack attached")
            def detachRack(rackName):
            
                req = DetachLink.Request()
                req.model1_name =  'ebot'     
                req.link1_name  = 'ebot_base_link'       
                req.model2_name =  rackName       
                req.link2_name  = 'link'  
                
                dockingNode.future = dockingNode.lind_detached_cli.call_async(req)
                while dockingNode.future is None :
                    stopBot(0.1)
                print("Rack detached")
            def rackAttach():
                # self.UltraOrientation()
                # stopBot(0.1)
                self.UltraOrientationLinear()
                stopBot(0.1)
                stopBot(0.15,-0.05,0.0)
                stopBot(0.1)
                attachRack(self.rackName)
            for i in range(2):
                self.moveBot(0.0,0.0)   
                twist = Twist()
                twist.linear.x = 0.0
                twist.angular.z = 0.0
                self.nav2speedPub.publish(twist)
                StopTime(0.1) 
            while ultrasonic_value[0] <2.0 or ultrasonic_value[1] < 2.0:
                StopTime(0.1)
                print("waitng for ultraSonic",ultrasonic_value)
            if self.isRackDetach:
                rackAttach()
                self.is_docking = False
                self.dock_aligned=True
                return None
            self.AngularDocking()
            stopBot(0.1)
            # #orientation done
            if self.isAttach:
                print(self.rackName,"rackName")
                rackAttach()
            else:
                self.odomLinearDocking()
                # stopBot(0.8,-0.2,0.0) 
                stopBot(0.4)
                self.cameraOrientation() 
                detachRack(self.rackName)
                stopBot(0.1)
            #     #linear done
            #     self.AngularDocking()
            #     stopBot(0.1)
            #     #orientation done
            #     print("is_robot_within_tolerance",self.is_robot_within_tolerance(robot_pose[0], robot_pose[1], robot_pose[2],self.targetX, self.targetY, self.targetYaw))
            #     if self.isAttach:
            #         self.switch_eletromagent(True)
            #     else :
            #         self.switch_eletromagent(False)
            #         stopBot(0.1,2.0,0.0)
            #         stopBot(0.1,0.0,0.0)
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
        self.isRackDetach = request.is_rack_detached
        self.BoxId = str(request.box_id)
        # Reset flags and start the docking process
        #
        #
        
        for i in range(2):
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
        
        response.message = "Docking control completed "
        print(request)
        return response

# Main function to initialize the ROS2 node and spin the executor
def main(args=None):
    
    my_robot_docking_controller = MyRobotDockingController()
    executor = MultiThreadedExecutor(3)
    executor.add_node(my_robot_docking_controller)
    executor_thread = Thread(target=executor.spin, daemon=True, args=())
    executor_thread.start()
    def ExitCallBack(msg):
        if msg.data == True:
            raise SystemExit
    exitDocking=my_robot_docking_controller.create_subscription(Bool, '/ExitNav',ExitCallBack, 10)
    try:
        rclpy.spin(my_robot_docking_controller)
    except SystemExit:
        print("SystemExit")
        my_robot_docking_controller.destroy_node()
        rclpy.shutdown()
        exit(0)
    my_robot_docking_controller.destroy_node()
    rclpy.shutdown()
    exit(0)
if __name__ == '__main__':
    main()