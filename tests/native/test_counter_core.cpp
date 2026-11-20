#include "device_core.h"
#include "fake_hardware.h"
#include <functional>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <vector>

namespace {
void require(bool b, const std::string& message) { if (!b) throw std::runtime_error(message); }
std::string json(JsonVariantConst v) { std::string s; serializeJson(v, s); return s; }
const std::string model = R"({"schema_version":1,"config":{"schema_version":1,"servos":[],"display":{"panel":"st7735s_128x160","sck":4,"mosi":5,"cs":15,"dc":7,"rst":6,"backlight":16,"rotation":1,"invert":false,"brightness":60}},"steps":[{"op":"display.begin","args":{}},{"op":"display.fill","args":{"color":0}},{"op":"display.text","args":{"text":"counter","x":8,"y":8,"color":65535}},{"op":"display.counter","args":{"name":"count","start":0,"step":1,"interval_ms":1000,"x":8,"y":48,"width":144,"height":20,"color":65535,"background":0}}]})";
class DisplayHardware : public FakeHardware {
 public:
  std::vector<std::string> text;
  int last_x = -1, last_y = -1, last_w = -1, last_h = -1;
  bool textDisplay(int x, int y, const std::string& value, uint16_t color) override {
    text.push_back(value); return FakeHardware::textDisplay(x, y, value, color);
  }
  bool rectDisplay(int x, int y, int w, int h, uint16_t color, bool fill) override {
    last_x=x;last_y=y;last_w=w;last_h=h;
    return FakeHardware::rectDisplay(x,y,w,h,color,fill);
  }
};
class Link {
 public:
  ai_maker::DeviceCore core;
  uint32_t now = 100;
  explicit Link(DisplayHardware& h, bool open=true) : core(h) { core.begin(); if (open) ok("session.open"); }
  JsonDocument call(const std::string& op, const std::string& args="{}") {
    JsonDocument req,a,r; deserializeJson(a,args,DeserializationOption::NestingLimit(24));
    req["kind"]="request";req["protocol_version"]=1;req["request_id"]="counter";req["session_id"]="test-counter";
    req["op"]=op;req["args"].set(a.as<JsonVariantConst>());
    require(!deserializeJson(r,core.process(json(req.as<JsonVariantConst>()),now)),"valid reply");return r;
  }
  JsonDocument ok(const std::string& op,const std::string& args="{}") {
    auto r=call(op,args);require(r["ok"].as<bool>(),op+": "+r["message"].as<std::string>());return r;
  }
  void save(const std::string& body=model) {
    ok("maintenance.enter");ok("program.save","{\"program\":"+body+",\"loop\":false,\"autostart\":true}");ok("maintenance.exit");
  }
  void tick(uint32_t n) {now=n;core.tick(n);}
  int64_t value() {return ok("program.info")["data"]["counter"]["value"].as<int64_t>();}
};
void autonomous_seconds_skip_and_flash_stability() {
  DisplayHardware h; Link writer(h);writer.save();writer.ok("session.close");
  const auto saves=h.saves,program_saves=h.program_saves;const auto persisted=h.program_state;
  Link boot(h,false);boot.tick(100);boot.tick(101);require(h.text.back()=="0","show initial zero");
  boot.tick(1100);require(boot.value()==0,"do not increment before a full second");
  boot.tick(1101);require(boot.value()==1 && h.text.back()=="1","first full second");
  boot.tick(2101);require(boot.value()==2,"second");
  boot.tick(10101);require(boot.value()==10 && h.text.back()=="10","missed ticks catch up without drift");
  require(h.last_x==8&&h.last_y==48&&h.last_w==144&&h.last_h==20,"clear only counter rectangle");
  require(h.program_saves==program_saves&&h.saves==saves&&h.program_state==persisted,"never persist live increments");
  require(boot.ok("program.info")["data"]["running"].as<bool>(),"terminal counter keeps running without root loop");
}
void restart_and_disable_or_clear() {
  DisplayHardware h;Link writer(h);writer.save();writer.ok("session.close");
  Link first(h,false);first.tick(100);first.tick(101);first.tick(5101);require(first.value()==5,"before restart");
  Link reboot(h,false);reboot.tick(100);reboot.tick(101);require(reboot.value()==0,"restart from saved start");
  reboot.ok("session.open");require(!reboot.ok("program.info")["data"]["counter"]["active"].as<bool>(),"host takeover stops counter");
  reboot.ok("maintenance.enter");reboot.ok("program.disable");reboot.ok("maintenance.exit");reboot.ok("session.close");
  Link disabled(h,false);disabled.tick(100);require(!disabled.ok("program.info")["data"]["running"].as<bool>(),"disabled boot");
  disabled.ok("session.open");disabled.ok("maintenance.enter");disabled.ok("program.clear");disabled.ok("maintenance.exit");disabled.ok("session.close");
  Link cleared(h,false);cleared.tick(100);require(!cleared.ok("program.info")["data"]["saved"].as<bool>(),"clear persists");
}
void timer_wraparound_and_int64_boundary() {
  DisplayHardware h;Link writer(h);writer.save();writer.ok("session.close");
  Link boot(h,false);uint32_t start=0xffffff00u;boot.tick(start);boot.tick(start+1);
  boot.tick(start+1000);require(boot.value()==0,"wrapbefore");boot.tick(start+1001);require(boot.value()==1,"wrapafter");
  boot.tick(start+5001);require(boot.value()==5,"wrapskip");
  boot.ok("session.open");JsonDocument p;deserializeJson(p,model);
  p["steps"][3]["args"]["start"]=std::numeric_limits<int64_t>::max()-1;
  boot.save(json(p.as<JsonVariantConst>()));boot.ok("program.start");boot.tick(6000);boot.tick(6001);boot.tick(7001);
  require(boot.value()==std::numeric_limits<int64_t>::max(),"exact max64 value");
  boot.tick(8001);auto info=boot.ok("program.info");
  require(!info["data"]["running"].as<bool>()&&!info["data"]["counter"]["active"].as<bool>()&&info["data"]["error"]!="","overflow stops instead of wrapping");
}
void render_failure_stops_and_preserves_saved_model() {
  DisplayHardware h;Link writer(h);writer.save();writer.ok("session.close");
  Link boot(h,false);boot.tick(100);boot.tick(101);const auto saved=h.program_state;
  h.output_ok=false;boot.tick(1101);auto info=boot.ok("program.info");
  require(!info["data"]["running"].as<bool>()&&info["data"]["error"]!="","draw failure visible");
  require(h.program_state==saved,"no faulty runtime persistence");
  h.output_ok=true;boot.ok("session.open");boot.ok("program.start");boot.tick(1102);boot.tick(1103);require(boot.value()==0,"explicit restart resets");
}
void loop_policy_rejected_both_save_and_load() {
  DisplayHardware h;Link live(h);live.ok("maintenance.enter");
  auto r=live.call("program.save","{\"program\":"+model+",\"loop\":true,\"autostart\":true}");
  require(!r["ok"].as<bool>()&&r["code"]=="PROGRAM_INVALID"&&h.program_saves==0,"root loop rejected before storage");
  live.save();JsonDocument record;deserializeJson(record,h.program_state);record["loop"]=true;h.program_state=json(record.as<JsonVariantConst>());
  Link boot(h,false);boot.tick(100);auto info=boot.ok("program.info");
  require(!info["data"]["running"].as<bool>()&&info["data"]["error"]!="","bad saved policy cannot autostart");
}
void explicit_owner_expiry_and_close_stop_ticker() {
  for (bool expiry:{false,true}) {
    DisplayHardware h;Link live(h);live.save();live.ok("program.start");live.tick(101);live.tick(102);
    require(live.ok("program.info")["data"]["counter"]["active"].as<bool>(),"explicit active");
    if (expiry) {live.tick(6102);require(!live.ok("program.info")["data"]["counter"]["active"].as<bool>(),"expiry");}
    else {live.ok("session.close");require(!live.ok("program.info")["data"]["counter"]["active"].as<bool>(),"close");}
  }
}
}
int main() {
  const std::vector<std::pair<const char*,std::function<void()>>> tests={
    {"autonomous_seconds_skip_and_flash_stability",autonomous_seconds_skip_and_flash_stability},
    {"restart_and_disable_or_clear",restart_and_disable_or_clear},
    {"timer_wraparound_and_int64_boundary",timer_wraparound_and_int64_boundary},
    {"render_failure_stops_and_preserves_saved_model",render_failure_stops_and_preserves_saved_model},
    {"loop_policy_rejected_both_save_and_load",loop_policy_rejected_both_save_and_load},
    {"explicit_owner_expiry_and_close_stop_ticker",explicit_owner_expiry_and_close_stop_ticker}};
  int failed=0;for(const auto& test:tests){try{test.second();std::cout<<"PASS "<<test.first<<'\n';}catch(const std::exception& e){++failed;std::cout<<"FAIL "<<test.first<<": "<<e.what()<<'\n';}}
  std::cout<<tests.size()<<" counter-core groups, "<<failed<<" failures\n";return failed?1:0;
}
