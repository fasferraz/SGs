# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#
#     Simple MSS SGs Server
#     ---------------------
#
#   -> only one SCTP session 
#   -> only one user (i.e. IMSI)
#
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

import random
import socket
import struct
import time
import select
from optparse import OptionParser

from binascii import hexlify, unhexlify

import sys
import os
import subprocess

import datetime

gsm = ("@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà")
ext = ("````````````````````^```````````````````{}`````\\````````````[~]`|````````````````````````````````````€``````````````````````````")

NETWORK_NAME = '[Banana Operator]'

MCC = '123'
MNC = '456'
VLR_NAME = 'mss.epc.mnc' + MNC + '.mcc' + MCC + '.3gppnetwork.org'


#
#   SGs Messages Codes (29.118):
#
#	1 SGsAP-PAGING-REQUEST	             - from MSS to MME: Request <<<<<< ------------------- Can by sent by this app
#	2 SGsAP-PAGING-REJECT	             - from MME to MSS: Answer to 1 (no success)
#	6 SGsAP-SERVICE-REQUEST	             - from MME to MSS: Answer to 1 (success)
#	7 SGsAP-DOWNLINK-UNITDATA	         - from MSS to MME  <<<<<< --------------------------- Can by sent by this app
#	8 SGsAP-UPLINK-UNITDATA	             - from MME to MSS  >>>>>> --------------------------- Processed by this app
#	9 SGsAP-LOCATION-UPDATE-REQUEST	     - from MME to MSS: Request -------------------------- Processed by this app
#	10 SGsAP-LOCATION-UPDATE-ACCEPT	     - from MSS to MME: Answer to 9 (success)
#	11 SGsAP-LOCATION-UPDATE-REJECT	     - from MSS to MME: Answer to 9 (no success)
#	12 SGsAP-TMSI-REALLOCATION-COMPLETE	 - from MME to MSS: Answer to 10 (confirm new tmsi)
#	13 SGsAP-ALERT-REQUEST	             - from MSS to MME: Request <<<<<< ------------------- Can by sent by this app
#	14 SGsAP-ALERT-ACK	                 - from MME to MSS: Answer to 13 (success)
#	15 SGsAP-ALERT-REJECT	             - from MME to MSS: Answer to 13 (no success)
#	16 SGsAP-UE-ACTIVITY-INDICATION	     - from MME to MSS: 
#	17 SGsAP-EPS-DETACH-INDICATION	     - from MME to MSS: Request >>>>>>
#	18 SGsAP-EPS-DETACH-ACK	             - from MSS to MME: Answer to 17
#	19 SGsAP-IMSI-DETACH-INDICATION      - from MME to MSS: Request >>>>>>
#	20 SGsAP-IMSI-DETACH-ACK	         - from MSS to MME: Answer to 19
#	21 SGsAP-RESET-INDICATION	         - from MSS to MME: Request <<<<<< ------------------- Can by sent by this app
#	22 SGsAP-RESET-ACK	                 - from MME to MSS: Answer to 21
#	23 SGsAP-SERVICE-ABORT-REQUEST	     - from MSS to MME: 
#	24 SGsAP-MO-CSFB-INDICATION	         - from MME to MSS: 
#	26 SGsAP-MM-INFORMATION-REQUEST	     - from MMS to MME: Request <<<<<< ------------------- Can by sent by this app (sent in Location-Update procedure)
#	27 SGsAP-RELEASE-REQUEST             - from MSS to MME
#	29 SGsAP-STATUS	                     - from MSS to MME:
#	31 SGsAP-UE-UNREACHABLE	             - from MME to MSS:


def binary2bytes(s):
    return bytes(int(s[i : i + 8], 2) for i in range(0, len(s), 8))

def splitbytes(b):
    return bytes(b[i] for i in range(len(b)-1,-1, -1))    

def gsm_encode(plaintext):
    res = ""
    for c in plaintext:
        idx = gsm.find(c)
        #print(c, idx)
        if idx != -1:
            res = '{0:08b}'.format(idx)[-7:] + res
            #print (res, len(res))
            continue
        idx = ext.find(c)
        if idx != -1:
            res = '{0:08b}'.format(27)[-7:] + res
            res = '{0:08b}'.format(idx)[-7:] + res
    
    spare_bits = (8 - len(res)%8) %8
    #print(spare_bits)
    res = '0'*spare_bits + res    
    
    return splitbytes(binary2bytes(res)), spare_bits
    


def handle_decode(decode):  #MME to MSS: Only processes messages that need answer
    global session_dict
    
    answer_list = [None]
    
    if decode[0] == 9: #location-update-request
        
        if 1 in decode and 4 in decode:
            #location-update-accept
            answer = b'\x0a'
            tmsi = b'\x0e\x05\xf4' + struct.pack('!I', random.randrange(pow(2,32)-1))
            answer += decode[1] + decode[4] + tmsi
            answer_list.append(answer)
            
            session_dict['tmsi'] = b'\x03\x04' + tmsi[-4:]
            session_dict['imsi'] = decode[1]
            session_dict['lai'] = decode[4]
            session_dict['mme'] = b'\x09' + bytes([len(decode[9])]) + decode[9]
            
            #mm-information-request
            gsm_text, spare_bits = gsm_encode(NETWORK_NAME)
            answer =  b'\x1a'
            answer += decode[1]
            
            answer += b'\x17' + bytes([17+2*len(gsm_text)])
            answer += b'\x43' + bytes([1+len(gsm_text)]) + bytes([128+spare_bits]) + gsm_text 
            answer += b'\x45' + bytes([1+len(gsm_text)]) + bytes([128+spare_bits]) + gsm_text    
            answer += b'\x47' + universal_time_and_local_time_zone()
            answer += b'\x49\x01\x00' # dst            
            answer_list.append(answer)            
            
    
    elif decode[0] == 17: # eps-detach-indication
        if 1 in decode:
            answer = b'\x12'
            answer += decode[1]
            answer_list.append(answer)    
    
    elif decode[0] == 19: #imsi-detach-indication
        if 1 in decode:
            answer = b'\x14'
            answer += decode[1]
            answer_list.append(answer)    

    elif decode[0] == 21: #reset-indication
        if 1 in decode:
            answer = b'\x16'
            answer += session_dict['vlr']
            answer_list.append(answer)   


    elif decode[0] == 8: #sms
        if 1 in decode and 22 in decode:        
            if decode[22][3:4] != b'\x04' and decode[22][3:4] != b'\x10':
                answer = b'\x07'
                answer += decode[1]                
                answer += b'\x16\x00' # length with zero. we put the length in the end.
                
                init_len = len(answer)
                if decode[22][2] > 128:
                    answer += bytes([decode[22][2]-128]) + b'\x04'
                else:
                    answer += bytes([decode[22][2]+128]) + b'\x04'

                nas_len = len(answer)-init_len
                answer = bytearray(answer)
                answer[init_len-1] = nas_len
                answer_list.append(answer)
                
                if decode[22][2] < 128:  
                    answer = b'\x07'
                    answer += decode[1]  
                    answer += b'\x16\x00' # length with zero. we put the len in the end.
                    init_len = len(answer)
                    
                    rp_message_reference = decode[22][6:7]
                    answer += bytes([decode[22][2]+128]) + b'\x01\x0d\x03'+ rp_message_reference
                    answer += b'\x41\x09\x01\x00' + universal_time_and_local_time_zone()
                   
                    nas_len = len(answer)-init_len
                    answer = bytearray(answer)
                    answer[init_len-1] = nas_len
                    answer_list.append(answer)       

    return answer_list


def universal_time_and_local_time_zone():
    return bcd(time.strftime("%Y%m%d%H%M%S")[2:]) + b'\x00'

def bcd(chars):
    bcd_string = ""
    for i in range(len(chars) // 2):
        bcd_string += chars[1+2*i] + chars[2*i]
    bcd_bytes = bytearray.fromhex(bcd_string)
    return bcd_bytes       




def handle_send(message):
    global session_dict
    

    request_list = [None]
    
    if message == 1: #paging sms
        if session_dict['imsi'] is not None and session_dict['tmsi'] is not None and session_dict['lai'] is not None:
            request = b'\x01'
            request += session_dict['imsi']
            request += session_dict['vlr']
            request += b'\x20\x01\x02'
            request += session_dict['tmsi']
            request += session_dict['lai']
            request_list.append(request)

    if message == 2: #paging cs call
        if session_dict['imsi'] is not None and session_dict['tmsi'] is not None and session_dict['lai'] is not None:
            request = b'\x01'
            request += session_dict['imsi']
            request += session_dict['vlr']
            request += b'\x20\x01\x01'
            request += session_dict['tmsi']
            request += b'\x1c\x07\x01\x80\x12\x05\x00\x83\xf4'
            request += session_dict['lai']
            request_list.append(request)
            
    elif message == 3: #sms

        if session_dict['imsi'] is not None:

            request = b'\x07'
            request += session_dict['imsi']
            #example sms#
            request += b'\x16\x27\x09\x01\x24\x01\x01\x07\x91\x53\x91\x26\x01\x00\x00\x00\x18\x04\x0c\x91\x53\x91\x66\x78\x92\x30\x00\x00\x02\x50\x50\x71\x84\x03\x40\x05\xd4\xf2\x9c\x5e\x06'
            request_list.append(request)

    elif message == 4: #alert
            request = b'\x0d'
            request += session_dict['imsi']
            request_list.append(request)    

    elif message == 5: #reset
            request = b'\x15'
            request += session_dict['vlr']
            request_list.append(request)     
    
            
    return request_list


# Information Elements

# 1	    IMSI
# 2	    VLR name
# 3	    TMSI
# 4	    Location area identifier
# 5	    Channel Needed
# 6	    eMLPP Priority
# 7	    TMSI status
# 8	    SGs cause
# 9	    MME name
# 10    EPS location update type
# 11    Global CN-Id
# 14    Mobile identity
# 15    Reject cause
# 16	IMSI detach from EPS service type
# 17	IMSI detach from non-EPS service type
# 21	IMEISV
# 22	NAS message container
# 23	MM information
# 27	Erroneous message
# 28    CLI
# 29	LCS client identity
# 30	LCS indicator
# 31	SS code
# 32	Service indicator
# 33	UE Time Zone
# 34	Mobile Station Classmark 2
# 35	Tracking Area Identity
# 36	E-UTRAN Cell Global Identity
# 37	UE EMM mode
# 38	Additional paging indicators
# 39	TMSI based NRI container
# 40	Selected CS domain operator
# 41	Maximum UE Availability Time
# 42	SM Delivery Timer
# 43	SM Delivery Start Time
# 44	Additional UE Unreachable indicators
# 45	Maximum Retransmission Time
# 46	Requested Retransmission Time

def sgs_decode(buffer):
    decode = {}
    
    decode[0] = buffer[0]
    pointer = 1
    while pointer < len(buffer):
        if buffer[pointer] not in decode: #just catch new LAI (first occurrence). old LAI uses same Information Element ID but is not needed
            decode[buffer[pointer]] = buffer[pointer:pointer+2+buffer[pointer+1]]
        pointer += 2 + buffer[pointer+1]

    return decode


def Menu():
    os.system('clear')
    print("Choose one of the options:\n\n\t1. SMS Paging\n\t2. CS Paging\n\t3. Send SMS\n\t4. Send Alert\n\t5. Send Reset\n\n")
    print("\tq. Quit\n")

def main():

    global server, session_dict
    
    session_dict = {}
    session_dict['imsi'] = None
    session_dict['tmsi'] = None
    session_dict['lai'] = None    
    
    
    vlr_bytes = bytes()
    vlr_l = VLR_NAME.split(".") 
    for word in vlr_l:
        vlr_bytes += struct.pack("!B", len(word)) + word.encode()    
    session_dict['vlr'] = b'\x02' + bytes([len(vlr_bytes)]) + vlr_bytes
    #session_dict['vlr'] = b'\x02' + bytes([len(VLR_NAME)]) + VLR_NAME
    
    parser = OptionParser()    
    parser.add_option("-i", "--ip", dest="mss_ip", help="MSS Local IP Address")

    (options, args) = parser.parse_args()
    
    if options.mss_ip is None:
        print('MMS IP Required. Exiting.')
        exit(1)  
        
        
    server_address = (options.mss_ip, 29118)

    #socket options
    server = socket.socket(socket.AF_INET,socket.SOCK_STREAM,socket.IPPROTO_SCTP) 
    server.bind(server_address)
    
    sctp_default_send_param = bytearray(server.getsockopt(132,10,32))
    sctp_default_send_param[11]= 0  #PPI = 0
    server.setsockopt(132, 10, sctp_default_send_param)

    server.listen()

    client, address = server.accept()
  
   
    socket_list = [sys.stdin ,client]
    
    while True:
        Menu()
        read_sockets, write_sockets, error_sockets = select.select(socket_list, [], [])
        
        for sock in read_sockets:
            if sock == client:
                buffer = client.recv(4096)
                answer_list = handle_decode(sgs_decode(buffer))
                for i in answer_list:
                    if i is not None:
                        client.send(i)
                        
            elif sock == sys.stdin:        
                msg = sys.stdin.readline()
                if msg == "q\n":
                    exit(1)
                elif msg[:-1].isdigit() == True:
                              
                    request_list = handle_send(int(msg[:-1]))
                    for i in request_list:
                        if i is not None:
                            client.send(i)


    server.close()




if __name__ == "__main__":    
    main()
