#!/usr/bin/env python3
"""
Example of adding and removing a collision object with a mesh geometry.
Note: Python module `trimesh` is required for this example (`pip install trimesh`).
`ros2 run pymoveit2 ex_collision_object.py --ros-args -p action:="add" -p position:="[0.5, 0.0, 0.5]" -p quat_xyzw:="[0.0, 0.0, -0.707, 0.707]"`
`ros2 run pymoveit2 ex_collision_object.py --ros-args -p action:="add" -p filepath:="./my_favourity_mesh.stl"`
`ros2 run pymoveit2 ex_collision_object.py --ros-args -p action:="remove"`
"""

from os import path
from threading import Thread

import time

import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.node import Node

from pymoveit2 import MoveIt2
from pymoveit2.robots import ur5
import tf2_ros

class ArucoBoxPose:
    def __init__(self):
        self.position = None
        self.quaternions = None


def main():
    rclpy.init()

    Initial_Pose = ArucoBoxPose()
    Initial_Pose.position = [0.18, 0.10, 0.46]
    Initial_Pose.quaternions = [0.50479, 0.495985, 0.499407, 0.499795]

    P1 = ArucoBoxPose()
    P1.position = [0.35, 0.1, 0.68]
    P1.quaternions = [0.50479, 0.495985, 0.499407, 0.499795]

    P2 = ArucoBoxPose()
    P2.position = [0.194, -0.43, 0.701]
    P2.quaternions = [ 0.7657689, 0.0, 0.0, 0.6431158 ]

    Drop = ArucoBoxPose()
    Drop.position = [-0.37, 0.12, 0.397]
    Drop.quaternions = [ 0.5414804, -0.4547516, -0.5414804, 0.4547516 ]

    # Create node for this example
    node = Node("pick_aruco")

    # Create callback group that allows execution of callbacks in parallel without restrictions
    callback_group = ReentrantCallbackGroup()

    # Create MoveIt 2 interface
    moveit2 = MoveIt2(
        node=node,
        joint_names=ur5.joint_names(),
        base_link_name=ur5.base_link_name(),
        end_effector_name=ur5.end_effector_name(),
        group_name=ur5.MOVE_GROUP_ARM,
        callback_group=callback_group,
    )

    # Spin the node in background thread(s)
    executor = rclpy.executors.MultiThreadedExecutor(2)
    executor.add_node(node)
    executor_thread = Thread(target=executor.spin, daemon=True, args=())
    executor_thread.start()
    tf_buffer = tf2_ros.buffer.Buffer()
    tf_listener = tf2_ros.TransformListener(tf_buffer, node)
    time.sleep(1)
    transform = []

    while (len(transform) == 0):
        try:
            transform = tf_buffer.lookup_transform(
                "base_link", "tool0", rclpy.time.Time()
            )
            transform = [
                transform.transform.translation.x,
                transform.transform.translation.y,
                transform.transform.translation.z
            ]
        except Exception as e:

            print(e)
            pass
        time.sleep(0.2)
    print(transform)

    def moveToPose(position, quaternions, position_name):
        counter = 0
        position = [round(position[0], 2), round(position[1], 2), round(position[2], 2)]
        x, y, z, w = False, False, False, False
        currentPose = [0,0,0, 0]
        while x == False and y == False and z == False:
            counter += 1
            print("Moving to ", position_name, "    [Attempt: ", counter,"]")
            moveit2.move_to_pose(position=position, quat_xyzw=quaternions, cartesian=False)
            moveit2.wait_until_executed()
            try:
                transform = tf_buffer.lookup_transform("base_link", "tool0", rclpy.time.Time())
                currentPose[0] = round(transform.transform.translation.x, 2)
                currentPose[1] = round(transform.transform.translation.y, 2)
                currentPose[2] = round(transform.transform.translation.z, 2)
                currentPose[3] = transform.header.stamp.sec
                print("Current Pose:",currentPose, "Target Pose:", position, "Time:", currentPose[3])
                # transform = tf_buffer.lookup_transform(
                #     "base_link", "tool0", rclpy.time.Time()
        
                # transform = [
                #     transform.transform.translation.x,
                #     transform.transform.translation.y,
                #     transform.transform.translation.z
                # ]
            except Exception as e:
                print(e)
            time.sleep(0.05)
            x = True if(currentPose[0] - position[0]) == 0.00 else False
            y = True if(currentPose[1] - position[1]) == 0.00 else False
            z = True if(currentPose[2] - position[2]) == 0.00 else False 
            print("x:",x,"y:",y,"z:",z)

    # Move to P1
    moveToPose(P1.position, P1.quaternions, "P1")
    print("Reached P1")

    # # Move to Initial
    # moveToPose(Initial_Pose.position, Initial_Pose.quaternions, "Initial")
    # print("Reached Initial")

    # Move to Drop
    moveToPose(Drop.position, Drop.quaternions, "Drop")
    print("Reached Drop")

    # Move to P2
    moveToPose(P2.position, P2.quaternions, "P2")
    print("Reached P2")
    
    # # Move to Initial
    # moveToPose(Initial_Pose.position, Initial_Pose.quaternions, "Initial")
    # print("Reached Initial")

    # Move to Drop
    moveToPose(Drop.position, Drop.quaternions, "Drop")
    print("Reached Drop")

    # # Move to Initial
    # moveToPose(Initial_Pose.position, Initial_Pose.quaternions, "Initial")
    # print("Reached Initial")
    
    print("Done")
    rclpy.spin(node)
    rclpy.shutdown()
    exit(0)


if __name__ == "__main__":
    main()
