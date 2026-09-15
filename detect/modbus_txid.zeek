@load base/protocols/modbus
@load base/frameworks/notice

module CpsTwin;

export {
    redef enum Notice::Type += { Modbus_Transaction_Anomaly };
}

const approved_writer: addr = 192.168.100.10;
const max_pending_transactions: count = 256;
const allowed_function_codes: set[count] = set(3, 6);

type FlowState: record {
    last_tx: count &default=0;
    last_unit: count &default=0;
    pending: set[count];
};

global state: table[conn_id] of FlowState;

event modbus_message(c: connection, headers: ModbusHeaders, is_orig: bool) {
    if ( c$id !in state ) {
        local initial_pending: set[count] = set();
        state[c$id] = [$last_tx=headers$tid, $last_unit=headers$uid,
                       $pending=initial_pending];
    }
    local s = state[c$id];
    local bad = F;
    local why = "";
    if ( is_orig ) {
        if ( headers$tid in s$pending ) { bad = T; why = "duplicate transaction ID"; }
        if ( headers$tid < s$last_tx && s$last_tx - headers$tid < 65000 ) { bad = T; why = "transaction ID rollback"; }
        if ( |s$pending| >= max_pending_transactions ) {
            bad = T; why = "outstanding transaction limit reached";
        } else {
            add s$pending[headers$tid];
        }
    } else if ( headers$tid !in s$pending ) {
        bad = T; why = "response without matching request";
    } else {
        delete s$pending[headers$tid];
    }
    if ( s$last_unit != 0 && headers$uid != s$last_unit ) { bad = T; why = "unit ID changed"; }
    if ( headers$function_code !in allowed_function_codes ) { bad = T; why = "unexpected function code"; }
    if ( is_orig && headers$function_code == 6 && c$id$orig_h != approved_writer ) {
        bad = T; why = "setpoint write from unapproved source";
    }
    if ( bad ) NOTICE([$note=Modbus_Transaction_Anomaly, $conn=c, $msg=why]);
    s$last_tx = headers$tid;
    s$last_unit = headers$uid;
    state[c$id] = s;
}

event connection_state_remove(c: connection) {
    delete state[c$id];
}
