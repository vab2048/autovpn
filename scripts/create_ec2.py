#
# This script creates an EC2 instance in the specified subnet-id which must exist
# in the given vpc-id.
#
############################################################################################
# Useful pages for reference:
# - https://stackoverflow.com/a/49458914/5108857
#   - Explains that we use filters to search for the security group rather than
#     using the group_name paramter in the ec2 API because the ec2 GroupName parameter
#     only works with the default VPC and not with user made ones.
# - https://stackoverflow.com/a/23042901/5108875
#   - Explains that you need to use the security group ID rather than the security group name.
# - https://stackoverflow.com/a/19050770/5108875
#   - Explains that you need to create a NetworkInterfaceSpecification with
#     associate_public_ip_address=True in order to get a public IP at EC2 launch time.
############################################################################################

import time
import boto
import boto.ec2
import sys
from boto.ec2.networkinterface import NetworkInterfaceSpecification, NetworkInterfaceCollection

keyname=sys.argv[1]
instance_type=sys.argv[2]
region=sys.argv[3]
ami=sys.argv[4]
port=sys.argv[5]
subnet_id=sys.argv[6] if sys.argv[6] else None
vpc_id=sys.argv[7] if sys.argv[7] else None
tag_string=sys.argv[8] if sys.argv[8] else None

if not subnet_id or not vpc_id:
    raise Exception(
        "You must set the subnet_id and vpc_id. Current values are: '{}' and '{}'".format(
            subnet_id, vpc_id
        )
    )

ec2 = boto.ec2.connect_to_region(region) if region else boto.connect_ec2()

def generate_tag_dict(tag_string):
    """
    The tag_string is a string of k:v pairs delimitted by a comma.
    e.g. Name:vpn_instance,ResourceType:ec2, etc. 
    """
    # Initialise the dictionary we will return
    d = {}
    # Split the string into a list of k:v strings
    k_v_list = tag_string.split(',')
    # Loop over each k:v string
    for k_v_string in k_v_list:
        k_v = k_v_string.split(':')
        d[k_v[0]] = k_v[1]
    return d

tag_dict = generate_tag_dict(tag_string) if tag_string else {}

def create_sg(group_name,
              vpn_port,
              group_description="A group that allows VPN access",
              cidr="0.0.0.0/0",
              ssh_port="22",
              vpc_id=None):
    
    group = ec2.create_security_group(
        group_name,
        group_description,
        vpc_id=vpc_id)
    group.authorize('tcp',ssh_port,ssh_port,cidr)
    group.authorize('udp',vpn_port,vpn_port,cidr)
    return group

def auto_vpn(ami=ami,
                    instance_type=instance_type,
                    key_name=keyname,
                    group_name="vpn_2",
                    ssh_port="22",
                    vpn_port=port,
                    cidr="0.0.0.0/0",
                    tag_dict=tag_dict,
                    #tag="auto_vpc",
                    subnet_id=subnet_id,
                    vpc_id=vpc_id,
                    user_data=None):
    try:
        group = ec2.get_all_security_groups(filters={
            'group-name': group_name,
            'vpc-id': vpc_id
        })[0]
    except IndexError, e:
        # If there is an IndexError extracting from the returned list that means the
        # list is empty and so no security group exists which match the given filters.
        # Let's create the security group in that case.
        group = create_sg(group_name,
                          vpn_port,
                          group_description="A group that allows VPN access",
                          cidr=cidr,
                          ssh_port=ssh_port,
                          vpc_id=vpc_id)
    except ec2.ResponseError, e:
        if e.code == 'InvalidGroup.NotFound':
            group = create_sg(group_name,
                              vpn_port,
                              group_description="A group that allows VPN access",
                              cidr=cidr,
                              ssh_port=ssh_port,
                              vpc_id=vpc_id)
        else:
            raise
        
    if int(port) != int(1194):
        try:
            mgroup = ec2.get_all_security_groups(groupnames=[group_name], filters=sg_filters)[0]
            mgroup.authorize('udp',vpn_port,vpn_port,cidr)
        except ec2.ResponseError, e:
            if e.code == 'InvalidPermission.Duplicate':
                '''fail here'''
            else: 
                raise

    # In order to support the 'auto-assign public ip' feature we need to create a
    # NetworkInterfaceSpecification with the associate_public_ip_address flag set to True.
    # We also specify the subnet_id and security group here rather than with the call
    # to 'run_instances'.
    interface = NetworkInterfaceSpecification(subnet_id=subnet_id,
                                              groups=[ group.id ],
                                              associate_public_ip_address=True)
    reservation = ec2.run_instances(ami,
        key_name=key_name,
        instance_type=instance_type,
        network_interfaces=NetworkInterfaceCollection(interface),
        user_data=user_data
    )
    
    instance = reservation.instances[0]
    while instance.state != 'running':
        time.sleep(30)
        instance.update()
        for key, value in tag_dict.iteritems():
            instance.add_tag(key, value)

    global host
    host = instance.ip_address
    print "%s" % host
	

if __name__ == "__main__": 
    auto_vpn()
