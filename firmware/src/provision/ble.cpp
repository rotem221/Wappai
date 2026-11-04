// Wappai provisioning: encrypted LE Secure Connections + physical BOOT owner consent.
// User explicitly requested no passkey entry. Just Works does not provide MITM authentication.
// GATT commands never contain executable content. Credentials are never returned in responses.
#include "ble.h"
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLE2902.h>
#include <BLESecurity.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <WiFi.h>
#include "app/model.h"
#include "net/net.h"
static constexpr char SERVICE[]="57415050-4149-4000-8000-000000000001";
static BLECharacteristic *rx,*tx;
static Preferences prefs;
static QueueHandle_t commands;
static bool enabled=false;
static bool connected=false, authenticated=false, authorized=false;
static uint32_t code=0, deadline=0, scanSeen=0;
static String owner,pending;
static volatile bool prompt=false;
static bool approved=false, scanPending=false;
static void reply(const String &s) { if (!connected) return; tx->setValue(s.c_str()); tx->notify(); }
class Security : public BLESecurityCallbacks {
 uint32_t onPassKeyRequest() override { return code; }
 void onPassKeyNotify(uint32_t value) override { code=value; deadline=millis()+90000; prompt=true; }
 bool onSecurityRequest() override { return true; }
 bool onConfirmPIN(uint32_t) override { return false; } // Never silently accept numeric comparison.
 void onAuthenticationComplete(ble_gap_conn_desc *d) override { authenticated=d && d->sec_state.encrypted && d->sec_state.bonded; if (!authenticated) { prompt=false; authorized=false; } }
};
class ServerCallbacks : public BLEServerCallbacks {
 void onConnect(BLEServer*) override { connected=true; authenticated=false; authorized=false; pending=""; approved=false; }
 void onDisconnect(BLEServer*) override { connected=false; authenticated=false; authorized=false; prompt=false; pending=""; approved=false; if(enabled) BLEDevice::startAdvertising(); }
};
static constexpr char HELLO[]="{\"type\":\"hello\",\"v\":1,\"board\":\"ws-s3-175c\",\"wifi_bands\":[\"2.4\"]}";
class Replies : public BLECharacteristicCallbacks {
 void onRead(BLECharacteristic *c) override { c->setValue(HELLO); }
};
class Commands : public BLECharacteristicCallbacks {
 void onWrite(BLECharacteristic *c) override {
  if (!authenticated) return;
  String value=c->getValue();
  if (value.length()>512) return;
  String *s=new String(value);
  if (xQueueSend(commands,&s,0)!=pdTRUE) delete s;
 }
};
void provisioningBegin() {
 if(enabled) return;
 prefs.begin("wappai-owner",false); owner=prefs.getString("key","");
 commands=xQueueCreate(4,sizeof(String*));
 if (!BLEDevice::init("Wappai")) { Serial.println("BLE unavailable: insufficient memory"); return; }
 enabled=true;
 BLEDevice::setMTU(247);

 BLEDevice::setSecurityCallbacks(new Security());
 BLESecurity::setAuthenticationMode(ESP_LE_AUTH_REQ_SC_BOND);
 BLESecurity::setCapability(ESP_IO_CAP_NONE);
 BLESecurity::setForceAuthentication(false);
 BLESecurity::setInitEncryptionKey(ESP_BLE_ENC_KEY_MASK|ESP_BLE_ID_KEY_MASK);

 auto *server=BLEDevice::createServer(); server->setCallbacks(new ServerCallbacks());
 auto *service=server->createService(SERVICE);
 rx=service->createCharacteristic("57415050-4149-4000-8000-000000000002",BLECharacteristic::PROPERTY_WRITE|BLECharacteristic::PROPERTY_WRITE_ENC);
 rx->setAccessPermissions(ESP_GATT_PERM_WRITE_ENCRYPTED); rx->setCallbacks(new Commands());
 tx=service->createCharacteristic("57415050-4149-4000-8000-000000000003",BLECharacteristic::PROPERTY_READ|BLECharacteristic::PROPERTY_NOTIFY|BLECharacteristic::PROPERTY_READ_ENC);

 tx->setCallbacks(new Replies()); tx->setValue(HELLO);
 service->start(); auto *ad=BLEDevice::getAdvertising(); ad->addServiceUUID(SERVICE); ad->setScanResponse(true);
 ad->setMinInterval(800); ad->setMaxInterval(1600); ad->start();
}
bool provisioningPrompt() { return prompt; }
uint32_t provisioningCode() { return code; }
bool provisioningConfirm(bool allow) {
 if (!prompt || !pending.length() || !authenticated) return false;
 prompt=false;
 if (!allow) { pending=""; reply("{\"type\":\"denied\"}"); return true; }
 owner=pending; prefs.putString("key",owner); pending=""; approved=true; authorized=true;
 reply("{\"type\":\"paired\",\"board\":\"ws-s3-175c\"}"); return true;
}
void provisioningLoop() {
 if(!enabled) return;
 if (prompt && (int32_t)(millis()-deadline)>0) { prompt=false; pending=""; reply("{\"type\":\"expired\"}"); }
 String *raw=nullptr;
 if (xQueueReceive(commands,&raw,0)==pdTRUE) {
  JsonDocument d; auto error=deserializeJson(d,*raw); delete raw;
  if (error || !authenticated) return;
  String op=d["op"]|"";
  if(op=="claim") {
   String key=d["key"]|""; if(key.length()!=64) return;
   for(char c:key) if(!isxdigit(c)) return;
   if(owner.length()) {
    // Constant-time compare to avoid credential-prefix oracle.
    unsigned diff=0; for(size_t i=0;i<64;i++) diff|=(uint8_t)key[i]^(uint8_t)owner[i];
    authorized=diff==0; reply(authorized?"{\"type\":\"paired\"}":"{\"type\":\"owned\"}");
   } else { pending=key; prompt=true; deadline=millis()+60000; reply("{\"type\":\"confirm_on_device\"}"); }
   return;
  }
  if(!authorized) { reply("{\"type\":\"unauthorized\"}"); return; }
  if(op=="status") {
   JsonDocument result; result["type"]="wifi_status";
   bool joined=WiFi.status()==WL_CONNECTED;
   result["connected"]=joined;result["ssid"]=joined?WiFi.SSID():netSavedSsid();
   modelLock();result["failed"]=model.wifiSetup && !joined;result["error"]=model.wifiErr;modelUnlock();
   String response;serializeJson(result,response);reply(response);
  }
  else if(op=="scan") { modelLock(); model.scanReq=true; scanSeen=model.scanSeq; modelUnlock(); scanPending=true; }
  else if(op=="wifi") {
   String ss=d["ssid"]|"", pass=d["password"]|"";
   if(ss.length()<1 || ss.length()>32 || pass.length()>63 || (pass.length()>0 && pass.length()<8)) { reply("{\"type\":\"invalid_wifi\"}"); return; }
   reply("{\"type\":\"connecting\"}"); netSetWifi(ss,pass);
  } else if(op=="hub") {
   String url=d["url"]|"", token=d["token"]|"";
   if(!url.startsWith("wss://") || url.length()>160 || token.length()<24 || token.length()>128) return;
   netConfigure(url,token); reply("{\"type\":\"hub_saved\"}");
  }
 }
 if(scanPending && model.scanSeq!=scanSeen && !model.scanBusy) {
  scanPending=false;
  for(uint8_t i=0;i<model.nAps;i++) {
   JsonDocument d; d["type"]="network"; d["ssid"]=model.aps[i].ssid; d["rssi"]=model.aps[i].rssi; d["open"]=model.aps[i].open;
   String s; serializeJson(d,s); reply(s); delay(25);
  }
  reply("{\"type\":\"scan_complete\",\"band\":\"2.4\"}");
 }
}

void provisioningEnd() {
 if(!enabled) return; enabled=false;prompt=false;authorized=false;authenticated=false;
 // Arduino's NimBLE deinit deletes the server before draining disconnect
 // callbacks. Disconnect peers while the server is still alive to avoid UAF.
 BLEDevice::getAdvertising()->stop();
 auto *server=BLEDevice::getServer();
 if(server) {
  for(const auto &peer:server->getPeerDevices(false))server->disconnect(peer.first);
  uint32_t start=millis();
  while(server->getConnectedCount() && millis()-start<2000)delay(20);
  if(server->getConnectedCount()) {enabled=true;return;}
  delay(100);
 }
 connected=false;
 BLEDevice::deinit(false);
 String *raw;while(xQueueReceive(commands,&raw,0)==pdTRUE)delete raw;
 vQueueDelete(commands);commands=nullptr;rx=nullptr;tx=nullptr;
}
