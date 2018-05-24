"""
This python script is used to configure the DW1000 chip as an anchor for ranging functionalities. It must be used in conjunction with the RangingTAG script.
It requires the following modules: DW1000, DW1000Constants and monotonic.
"""


import DW1000
import monotonic
import DW1000Constants as C
from DW1000Device import DW1000Device


lastActivity = 0
protocolFailed = False
sentAck = False
receivedAck = False
LEN_DATA = 20
data = [0] * LEN_DATA
REPLY_DELAY_TIME_US = 7000 

tag_list = {}
# Contains the DW1000Device objects of type TAG 
expectedMsgId = {}
# Contains the expected message ID of the Devices as key value pairs. key = device address, value = expectedMsgId
# TODO: Implement this as an attribute of the DW1000Device object's attribute
myAddress = 100
anchorID = 100
# Current Device's Address


def millis():
    """
    This function returns the value (in milliseconds) of a clock which never goes backwards. It detects the inactivity of the chip and
    is used to avoid having the chip stuck in an undesirable state.
    """
    return int(round(monotonic.monotonic() * C.MILLISECONDS))


def handleSent():
    """
    This is a callback called from the module's interrupt handler when a transmission was successful.
    It sets the sentAck variable as True so the loop can continue.
    """
    global sentAck
    sentAck = True


def handleReceived():
    """
    This is a callback called from the module's interrupt handler when a reception was successful.
    It sets the received receivedAck as True so the loop can continue.
    """
    global receivedAck
    receivedAck = True


def noteActivity():
    """
    This function records the time of the last activity so we can know if the device is inactive or not.
    """
    global lastActivity
    lastActivity = millis()


def resetInactive():
    """
    This function restarts the default polling operation when the device is deemed inactive.
    """
    global expectedMsgId
    print("Reset inactive")
    for i in expectedMsgId.keys():
        expectedMsgId[i] = C.POLL
    receiver()
    noteActivity()


def transmitPollAck(address):
    """
    This function sends the polling acknowledge message which is used to confirm the reception of the polling message. 
    """        
    global data, myAddress
    print "transmitPollAck"
    DW1000.newTransmit()
    data[0] = C.POLL_ACK
    data[16] = myAddress
    data[17] = address
    DW1000.setDelay(REPLY_DELAY_TIME_US, C.MICROSECONDS)
    DW1000.setData(data, LEN_DATA)
    DW1000.startTransmit()


def transmitRangeAcknowledge(address):
    """
    This functions sends the range acknowledge message which tells the tag that the ranging function was successful and another ranging transmission can begin.
    """
    global data, myAddress, nodeType
    ##print "transmitRangeAcknowledge"
    DW1000.newTransmit()
    data[0] = C.RANGE_REPORT
    data[16] = myAddress
    data[17] = address
    sequence = tag_list[address].sequenceNumber
    DW1000.setTimeStamp(data, tag_list[address].timePollReceived[sequence], 1)
    DW1000.setTimeStamp(data, tag_list[address].timePollAckSent[sequence], 6)
    DW1000.setTimeStamp(data, tag_list[address].timeRangeReceived[sequence], 11)
    DW1000.setData(data, LEN_DATA)
    DW1000.startTransmit()


def transmitRangeFailed(address):
    """
    This functions sends the range failed message which tells the tag that the ranging function has failed and to start another ranging transmission.
    """
    global data, myAddress
    ##print "transmitRangeFailed"
    DW1000.newTransmit()
    data[0] = C.RANGE_FAILED
    data[16] = myAddress
    data[17] = address

    DW1000.setData(data, LEN_DATA)
    DW1000.startTransmit()


def receiver():
    """
    This function configures the chip to prepare for a message reception.
    """
    global data
    print "receiver"
    DW1000.newReceive()
    DW1000.receivePermanently()
    DW1000.startReceive()


def addTag(address):
    global tag_list, expectedMsgId

    tag_list[address] = DW1000Device(address, DW1000Device.TAG)
    expectedMsgId[address] = C.POLL


def loop():
    global sentAck, receivedAck, timePollAckSentTS, timePollReceivedTS, timePollSentTS, timePollAckReceivedTS, timeRangeReceivedTS, protocolFailed, data, expectedMsgId, timeRangeSentTS, tag_list, myAddress, nodeType

    if (sentAck == False and receivedAck == False):
        if ((millis() - lastActivity) > C.RESET_PERIOD):
            resetInactive()
        return

    if sentAck:
        sentAck = False
        msgId = data[0]
        tag = tag_list[data[17]]
        sequence = data[18]
        if msgId == C.POLL_ACK:
            print "Sending poll ack to {}".format(data[17])
            tag.timePollAckSent[sequence] = DW1000.getTransmitTimestamp()
            noteActivity()
        if msgId == C.RANGE_REPORT:
            print "Sending Range Report to {}".format(data[17])
            noteActivity()

    if receivedAck:
        receivedAck = False
        data = DW1000.getData(LEN_DATA)
        msgId           = data[0]
        sender          = data[16]
        receiver        = data[17]

        if nodeType != typeOfSender:
            # Only accept packets from tags
            # ignore packets from anchors...
            return
        if sender not in tag_list:
            print "Adding {} to tag list".format(sender)
            print data
            # Add tag to tag_list
            addTag(sender)
            # Send a dummy POLL_ACK so that the tag can add this anchor to its list and send data.
            transmitPollAck(sender)
            print tag_list
        else:
            # if receiver == 0xFF:
            #     print "Ignoring Broadcast Message by {}".format(sender)
            #     transmitPollAck(sender)
            #     return
            if receiver != myAddress:
                print "Message was for {} :(".format(receiver)
                print "expecting {}".format(expectedMsgId)
                # Message wasn't meant for us
                return
            # elif receiver == 0xFF:
            #     print "receiving broadcast message..!!"
            #     resetInactive()
            else:
                if msgId != expectedMsgId[sender]:
                    print "MessageID not expected :( got {} expected {}".format(msgId, expectedMsgId[sender])
                    print "protocolFailed"
                    protocolFailed = True
                tag = tag_list[sender]
                sequence = data[18]
                if msgId == C.POLL:
                    tag.sequenceNumber = sequence
                    print "Got poll for sequence", sequence
                    protocolFailed = False
                    tag.timePollReceived[sequence] = DW1000.getReceiveTimestamp()
                    expectedMsgId[sender] = C.RANGE
                    transmitPollAck(sender)
                    noteActivity()
                if msgId == C.RANGE:
                    print "Got Range report for sequence" , sequence
                    tag.timeRangeReceived[sequence] = DW1000.getReceiveTimestamp()
                    expectedMsgId[sender] = C.POLL
                    if protocolFailed == False:
                        # tag.timePollSent[sequence] = DW1000.getTimeStamp(data, 1)
                        # tag.timePollAckReceived[sequence] = DW1000.getTimeStamp(data, 6)
                        # tag.timeRangeSent[sequence] = DW1000.getTimeStamp(data, 11)
                        # print tag
                        transmitRangeAcknowledge(sender)
                        expectedMsgId[sender] = C.POLL

                        # distance = (tag_list[sender].getRange() % C.TIME_OVERFLOW) * C.DISTANCE_OF_RADIO
                        # print("Distance: %.2f m" %(distance))

                    else:
                        print "range failed"
                        transmitRangeFailed(sender)

        noteActivity()

try:
    PIN_IRQ = 19
    PIN_SS = 16
    DW1000.begin(PIN_IRQ)
    DW1000.setup(PIN_SS)
    ##print("DW1000 initialized")
    ##print("############### ANCHOR ##############")

    DW1000.generalConfiguration("82:17:5B:D5:A9:9A:E2:9C", C.MODE_SHORTDATA_FAST_ACCURACY)
    DW1000.registerCallback("handleSent", handleSent)
    DW1000.registerCallback("handleReceived", handleReceived)
    DW1000.setAntennaDelay(C.ANTENNA_DELAY_RASPI)

    receiver()
    noteActivity()
    while 1:
        loop()

except KeyboardInterrupt:
    DW1000.close()
