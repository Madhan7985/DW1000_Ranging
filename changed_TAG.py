"""
This python script is used to configure the DW1000 chip as a tag for ranging functionalities. It must be used in conjunction with the RangingAnchor script. 
It requires the following modules: DW1000, DW1000Constants and monotonic.
"""


import DW1000
import monotonic
import DW1000Constants as C
from DW1000Device import DW1000Device
import time

LEN_DATA = 21
data = [0] * LEN_DATA
protocolFailed = False
lastActivity = 0
lastPoll = 0
sentAck = False
receivedAck = False
REPLY_DELAY_TIME_US = 7000
# ALPHA = .000001
# k = 0
# The polling range frequency defines the time interval between every distance poll in milliseconds. Feel f q   ree to change its value. 
POLL_RANGE_FREQ = 100
# the distance between the tag and the anchor will be estimated every second.
# NOTE: I changed the value in the contant file ;)
expectedMsgId = {}
anchor_list = {}
# Address of this Device... Every device needs a unique adderss
# NOTE: Tags and anchors cannot have the same address
myAddress = 0 
SEQ_NO = 0
nodeType = 0 # TAG

NO_OF_ANCHORS = 1
t=0
# in_anchor_list = 0

def millis():
    """
    This function returns the value (in milliseconds) of a clock which never goes backwards. It detects the inactivity of the chip and
    is used to avoid having the chip stuck in an undesirable state.
    """
    return int(round(monotonic.monotonic()*C.MILLISECONDS))


def noteActivity():
    """
    This function records the time of the last activity so we can know if the device is inactive or not.
    """    
    global lastActivity
    lastActivity = millis()

def handleSent():
    """
    This is a callback called from the module's interrupt handler when a transmission was successful. 
    It sets the sentAck variable as True so the loop can continue.
    """        
    global sentAck
    sentAck = True
    noteActivity()


def handleReceived():
    """
    This is a callback called from the module's interrupt handler when a reception was successful. 
    It sets the received receivedAck as True so the loop can continue.
    """            
    global receivedAck
    receivedAck = True

def receiver():
    """
    This function configures the chip to prepare for a message reception.
    """    
    DW1000.newReceive()
    DW1000.receivePermanently()
    DW1000.startReceive()



def resetInactive():
    """
    This function restarts the default polling operation when the device is deemed inactive.
    """
    global expectedMsgId
    print("Reset inactive") 
    if expectedMsgId.keys() == [] :
        transmitPoll()
        noteActivity()
    else:
        for i in expectedMsgId.keys():
            transmitPoll(i)
            expectedMsgId[i] = C.POLL_ACK
        noteActivity()


def transmitPoll(address=0xFF):
    """
    This function sends the polling message which is the first transaction to enable ranging functionalities. 
    It checks if an anchor is operational.
    """    
    global data, lastPoll, nodeType, anchor_list, myAddress
    #print "polling"
    while (millis() - lastPoll < POLL_RANGE_FREQ):
        pass
    DW1000.newTransmit()
    data[0] = C.POLL
    data[16] = myAddress
    data[17] = address
    data[19] = nodeType
    
    if address != 0XFF:
        data[18] = anchor_list[address].sequenceNumber
        anchor_list[address].expectedmesg = C.RANGE
    DW1000.setData(data, LEN_DATA)
    DW1000.startTransmit()
    lastPoll = millis()
    noteActivity()


def transmitRange(address):
    """
    This function sends the range message containing the timestamps used to calculate the range between the devices.
    """
    global data, nodeType, myAddress, anchor_list
    #print "transmitting range"
    DW1000.newTransmit()
    data[0] = C.RANGE
    data[16] = myAddress
    data[17] = address
    data[18] = anchor_list[address].sequenceNumber
    data[19] = nodeType
    anchor_list[address].expectedmesg = C.POLL
    DW1000.setData(data, LEN_DATA)
    DW1000.startTransmit()
    noteActivity()


def addAnchor(address):
    global anchor_list, expectedMsgId

    anchor_list[address] = DW1000Device(address, DW1000Device.ANCHOR)
    expectedMsgId[address] = C.POLL_ACK
    anchor_list[address].expectedmesg = C.POLL
    noteActivity()

def nextAnchorWaitingFor(msgTypeWaitingFor):
    global anchor_list

    for i in anchor_list.values():
        if i.expectedmesg == msgTypeWaitingFor:
            return i.address
    return False


def loop():
    global sentAck, receivedAck, data, expectedMsgId, anchor_list, myAddress, protocolFailed, nodeType,t

    if (sentAck == False and receivedAck == False):
        if ((millis() - lastActivity) > C.RESET_PERIOD):
            resetInactive()
        return
    

    if ((millis() - lastActivity > POLL_RANGE_FREQ)) :
    	if anchor_list == {} :
    		noteActivity()
    		transmitPoll()
    	else :
    		for i in range(len(anchor_list)) :
    			noteActivity()
    			return transmitPoll(i.address)

    if sentAck:
        # if tag
        sentAck = False
        msgID = data[0]
        is_brodcast =  data[17] == 0xFF
        if not is_brodcast:
            anchor = anchor_list[data[17]]
            sequence = anchor.sequenceNumber
        if msgID == C.POLL:
            # Check if broadcast message
            if not is_brodcast:
                # print "Sending poll to {} with seq {}".format(data[17], anchor.sequenceNumber)
                anchor.timePollSent[sequence] = DW1000.getTransmitTimestamp()
                t = time.time()
                anchor.expectedmesg = C.RANGE
                expectedMsgId[data[17]] = C.POLL_ACK
                # print "time poll sent-->",anchor_list[data[17]].timePollSent 
            noteActivity()
        elif msgID == C.RANGE:
            # print "Range message sent to {} with seq {}".format(data[17], anchor.sequenceNumber)
            expectedMsgId[data[17]] = C.RANGE_REPORT
            anchor.expectedmesg = C.POLL
            anchor.timeRangeSent[sequence]   = DW1000.getTransmitTimestamp()
            # print "time range sent-->",anchor_list[data[17]].timeRangeSent[sequence] 
            noteActivity()

    if receivedAck:
        receivedAck = False
        data = DW1000.getData(LEN_DATA)
        msgID           = data[0]
        
        sender          = data[16]
        receiver        = data[17]
        sequence        = data[18]
        typeOfSender    = data[19]
        # print "msgID" , msgID , " " , 
        if nodeType == typeOfSender:
            # Only accept packets from anchors
            # ignore packets from tags...
            return
        # Check if sender is in anchor_list or not 
        if sender not in anchor_list:
            print "Adding {} to anchor list".format(sender)
            # Add anchor to anchor_list
            ###### if there are no anchors then... transmit poll
            addAnchor(sender)

            transmitPoll(sender)
            
            noteActivity()




            # Now Expecting a POLL_ACK from the added anchor
        else:
            # Check if message was intended for this TAG or not
            if receiver != myAddress:
                print "Message wasn't for me :("
                # Message wasn't for this tag, so we will ignore this 
                return
            else:
                # Message was meant for us 
                if msgID != expectedMsgId[sender]:
                    print "MessageID not expected :( got {} expected {}".format(msgID, expectedMsgId[sender])
                    protocolFailed = True
                    # Message ID received wasn'nt what we expected so resetting
                    expectedMsgId[sender] = C.POLL_ACK

                    transmitPoll(sender)
                    noteActivity()
                    return
                # Message ID is what we expected
                anchor = anchor_list[sender]

                if msgID == C.POLL_ACK:
                    protocolFailed = False
                    # print "Got poll ACK"
                    anchor.timePollAckReceived[sequence] = DW1000.getReceiveTimestamp()
                    # print "time poll ack received-->",anchor_list[data[16]].timePollAckReceived 
                    expectedMsgId[sender] = C.RANGE_REPORT
                    anchor_list[data[16]].expectedmesg = C.RANGE
                    ##### if there is any anchor which expects poll then send poll to that anchor
                    noteActivity()
                    if len(anchor_list) < NO_OF_ANCHORS :
                        noteActivity()
                    	return

                    else : 

	                    nextSender = nextAnchorWaitingFor(C.POLL)
	                    if not nextSender == False:
	                        # print "rabbit"
	                        # in_anchor_list = 1
	                        transmitPoll(nextSender)# in_anchor_list
                            
	                    ##### else transmitrange to this anchor
	                    else:
	                        # print "bear"
	                        transmitRange(sender)
	                    noteActivity()

                elif msgID == C.RANGE_REPORT :
                	if protocolFailed == False :
                        			# print "Got Range report"

						anchor.timePollReceived[sequence] = DW1000.getTimeStamp(data, 1)
						anchor.timePollAckSent[sequence] = DW1000.getTimeStamp(data, 6)
						anchor.timeRangeReceived[sequence] = DW1000.getTimeStamp(data, 11)

						distance = (anchor_list[sender].getRange() % C.TIME_OVERFLOW) * C.DISTANCE_OF_RADIO
						print("Distance: %.2f m %d" %(distance,sequence))
                        print (time.time() - t)
                        anchor.incrementSequenceNumber()
                        anchor.expectedmesg = C.POLL
                        expectedMsgId[sender] = C.POLL_ACK
                        anchor.deletePreviousSequenceData()
						##### if there is any anchor that expects range msg then send range to that anchor
                        nextSender = nextAnchorWaitingFor(C.RANGE)
                        if not nextSender == False:
                            transmitRange(nextSender)
                            
                        # noteActivity()
						##### else transmit poll to current anchor
						
                        else:
							# in_anchor_list = 1
							transmitPoll(sender)
							noteActivity() 

                elif msgID == C.RANGE_FAILED:
                    # print "range failed"
                    expectedMsgId[sender] = C.POLL_ACK
                    # in_anchor_list = 1
                    transmitPoll(sender)
        noteActivity()


try:
    PIN_IRQ = 19
    PIN_SS = 16
    DW1000.begin(PIN_IRQ)
    DW1000.setup(PIN_SS)
    # print("DW1000 initialized")
    # print("############### TAG ##############")   

    DW1000.generalConfiguration("7D:00:22:EA:82:60:3B:9C", C.MODE_LONGDATA_FAST_ACCURACY)
    DW1000.registerCallback("handleSent", handleSent)
    DW1000.registerCallback("handleReceived", handleReceived)
    DW1000.setAntennaDelay(C.ANTENNA_DELAY_RASPI)
    addAnchor(1) 
    # addAnchor(2)
    receiver()
    transmitPoll(1)
    noteActivity()
    while 1:
        loop()

except KeyboardInterrupt:
    DW1000.close()
