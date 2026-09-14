@load base/protocols/modbus
@load base/frameworks/notice

module CpsTwin;

export {
    redef enum Notice::Type += { Modbus_Transaction_Anomaly };
}

type FlowState: record {
    last_tx: count &default=0;
    last_unit: count &default=0;
    pending: set[count];
    last_fc: count &default=0;
};

global state: table[conn_id] of FlowState;

event modbus_message(c: connection, headers: ModbusHeaders, is_orig: bool) {
    if ( c$id !in state )
        state[c$id] = [$last_tx=headers$tid, $last_unit=headers$uid];
    local s = state[c$id];
    local bad = F;
    local why = "";
    if ( is_orig ) {
        if ( headers$tid in s$pending ) { bad = T; why = "duplicate transaction ID"; }
        if ( headers$tid < s$last_tx && s$last_tx - headers$tid < 65000 ) { bad = T; why = "transaction ID rollback"; }
        add s$pending[headers$tid];
    } else if ( headers$tid !in s$pending ) {
        bad = T; why = "response without matching request";
    } else {
        delete s$pending[headers$tid];
    }
    if ( s$last_unit != 0 && headers$uid != s$last_unit ) { bad = T; why = "unit ID changed"; }
    if ( s$last_fc == 16 && headers$fc == 3 && ! is_orig ) { bad = T; why = "unexpected write/read response transition"; }
    if ( bad ) NOTICE([$note=Modbus_Transaction_Anomaly, $conn=c, $msg=why]);
    s$last_tx = headers$tid;
    s$last_unit = headers$uid;
    s$last_fc = headers$fc;
    state[c$id] = s;
}

event connection_state_remove(c: connection) { delete state[c$id]; }
