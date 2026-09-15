use capi::sctypes::*;
use capi::scbehavior::*;
use capi::scdom::{HELEMENT};
use value::Value;
use dom::event::EventHandler;

#[repr(C)]
pub(crate) struct WindowHandler<T>
{
	pub hwnd: HWINDOW,
	pub handler: T,
}

#[repr(C)]
pub(crate) struct BoxedHandler {
	pub handler: Box<dyn EventHandler>,
}

fn is_detach_event(evtg: UINT, params: LPVOID) -> bool {
	let evtg : EVENT_GROUPS = unsafe { ::std::mem::transmute(evtg) };
	if evtg == EVENT_GROUPS::HANDLE_INITIALIZATION {
		assert!(!params.is_null());
		let scnm = params as *const INITIALIZATION_EVENTS;
		let cmd = unsafe { *scnm };
		if cmd == INITIALIZATION_EVENTS::BEHAVIOR_DETACH {
			return true;
		}
	}
	false
}

pub(crate) extern "system" fn _event_handler_window_proc<T: EventHandler>(tag: LPVOID, _he: ::capi::scdom::HELEMENT, evtg: UINT, params: LPVOID) -> BOOL
{
	let boxed = tag as *mut WindowHandler<T>;
	let tuple: &mut WindowHandler<T> = unsafe { &mut *boxed };

	let hroot: HELEMENT = if let Ok(root) = ::dom::Element::from_window(tuple.hwnd) {
		root.as_ptr()
	} else {
		::std::ptr::null_mut()
	};

	// custom initialization (because there is no DOM in plain window)
	if is_detach_event(evtg, params) {
		tuple.handler.detached(hroot);

		// here we drop our tuple
		let ptr = unsafe { Box::from_raw(boxed) };
		drop(ptr);

		return true as BOOL;
	}

	process_events(&mut tuple.handler, hroot, evtg, params)
}

pub(crate) extern "system" fn _event_handler_behavior_proc(tag: LPVOID, he: HELEMENT, evtg: UINT, params: LPVOID) -> BOOL {
	// reconstruct pointer to Handler
	let boxed = tag as *mut BoxedHandler;
	let me = unsafe { &mut *boxed };
	let me = &mut *me.handler;

	if is_detach_event(evtg, params) {
		me.detached(he);

		// here we drop our handler
		let ptr = unsafe { Box::from_raw(boxed) };
		drop(ptr);

		return true as BOOL;
	}

	process_events(me, he, evtg, params)
}

pub(crate) extern "system" fn _event_handler_proc<T: EventHandler>(tag: LPVOID, he: HELEMENT, evtg: UINT, params: LPVOID) -> BOOL
{
	// reconstruct pointer to Handler
	let boxed = tag as *mut T;
	let me = unsafe { &mut *boxed };

	if is_detach_event(evtg, params) {
		me.detached(he);

		// here we drop our handler
		let ptr = unsafe { Box::from_raw(boxed) };
		drop(ptr);

		return true as BOOL;
	}

	process_events(me, he, evtg, params)
}

// Newer Sciter DLLs may report events absent from these pinned bindings.
// Returning unhandled lets Sciter continue dispatch without constructing an invalid enum.
fn checked_behavior_event(raw: UINT) -> Option<BEHAVIOR_EVENTS> {
    use capi::scbehavior::BEHAVIOR_EVENTS::*;
    const KNOWN: &[BEHAVIOR_EVENTS] = &[
        BUTTON_CLICK,
        BUTTON_PRESS,
        BUTTON_STATE_CHANGED,
        EDIT_VALUE_CHANGING,
        EDIT_VALUE_CHANGED,
        SELECT_SELECTION_CHANGED,
        SELECT_VALUE_CHANGED,
        POPUP_REQUEST,
        POPUP_READY,
        POPUP_DISMISSED,
        MENU_ITEM_ACTIVE,
        MENU_ITEM_CLICK,
        CONTEXT_MENU_REQUEST,
        VISIUAL_STATUS_CHANGED,
        DISABLED_STATUS_CHANGED,
        POPUP_DISMISSING,
        CONTENT_CHANGED,
        CLICK,
        CHANGE,
        MEDIA_CHANGED,
        INPUT_LANGUAGE_CHANGED,
        CONTENT_MODIFIED,
        READONLY_STATUS_CHANGED,
        ARIA_LIVE_AREA_CHANGED,
        HYPERLINK_CLICK,
        PASTE_TEXT,
        PASTE_HTML,
        ELEMENT_COLLAPSED,
        ELEMENT_EXPANDED,
        ACTIVATE_CHILD,
        UI_STATE_CHANGED,
        FORM_SUBMIT,
        FORM_RESET,
        DOCUMENT_COMPLETE,
        HISTORY_PUSH,
        HISTORY_DROP,
        HISTORY_PRIOR,
        HISTORY_NEXT,
        HISTORY_STATE_CHANGED,
        CLOSE_POPUP,
        TOOLTIP_REQUEST,
        ANIMATION,
        DOCUMENT_CREATED,
        DOCUMENT_CLOSE_REQUEST,
        DOCUMENT_CLOSE,
        DOCUMENT_READY,
        DOCUMENT_PARSED,
        VIDEO_INITIALIZED,
        VIDEO_STARTED,
        VIDEO_STOPPED,
        VIDEO_BIND_RQ,
        PAGINATION_STARTS,
        PAGINATION_PAGE,
        PAGINATION_ENDS,
        CUSTOM,
        MOUNT_COMPONENT,
        FIRST_APPLICATION_EVENT_CODE,
    ];
    KNOWN.iter().copied().find(|code| *code as UINT == raw)
}

fn process_events(me: &mut dyn EventHandler, he: HELEMENT, evtg: UINT, params: LPVOID) -> BOOL
{
	let evtg : EVENT_GROUPS = unsafe { ::std::mem::transmute(evtg) };
	if he.is_null()
		&& evtg != EVENT_GROUPS::SUBSCRIPTIONS_REQUEST
		&& evtg != EVENT_GROUPS::HANDLE_BEHAVIOR_EVENT
		&& evtg != EVENT_GROUPS::HANDLE_INITIALIZATION
		&& evtg != EVENT_GROUPS::HANDLE_SOM
	{
		eprintln!("[sciter] warning! null element for {:04X}", evtg as u32);
	}

	let result = match evtg {

		EVENT_GROUPS::SUBSCRIPTIONS_REQUEST => {
			assert!(!params.is_null());
			let scnm = params as *mut EVENT_GROUPS;
			let nm = unsafe {&mut *scnm};
			let handled = me.get_subscription();
			if let Some(needed) = handled {
				*nm = needed;
			}
			handled.is_some()
		},

		EVENT_GROUPS::HANDLE_INITIALIZATION => {
			assert!(!params.is_null());
			let scnm = params as *mut INITIALIZATION_PARAMS;
			let nm = unsafe { &mut *scnm };
			match nm.cmd {
				INITIALIZATION_EVENTS::BEHAVIOR_DETACH => {
					me.detached(he);
				},

				INITIALIZATION_EVENTS::BEHAVIOR_ATTACH => {
					me.attached(he);
				},
			};
			true
		},

		EVENT_GROUPS::HANDLE_SOM => {
			assert!(!params.is_null());
			let scnm = params as *mut SOM_PARAMS;
			let nm = unsafe { &mut *scnm };
			match nm.cmd {
				SOM_EVENTS::SOM_GET_PASSPORT => {
					if let Some(asset) = me.get_asset() {
						nm.result.passport = asset.get_passport();
						return true as BOOL;
					}
				},

				SOM_EVENTS::SOM_GET_ASSET => {
					if let Some(asset) = me.get_asset() {
						nm.result.asset = asset;
						return true as BOOL;
					}
				},
			};
			false
		},


		EVENT_GROUPS::HANDLE_BEHAVIOR_EVENT => {
			assert!(!params.is_null());
			let scnm = params as *const BEHAVIOR_EVENT_PARAMS;
			let nm = unsafe { &*scnm };

      use dom::event::EventReason;
			let code = match checked_behavior_event(nm.cmd & 0x0_0FFF) {
				Some(code) => code,
				None => return 0,
			};
			let phase = match nm.cmd & 0xFFFF_F000 {
				0 => PHASE_MASK::BUBBLING,
				0x8000 => PHASE_MASK::SINKING,
				0x10000 => PHASE_MASK::BUBBLING_HANDLED,
				0x18000 => PHASE_MASK::SINKING_HANDLED,
				_ => return 0,
			};
			let reason = match code {
				BEHAVIOR_EVENTS::EDIT_VALUE_CHANGED | BEHAVIOR_EVENTS::EDIT_VALUE_CHANGING => {
					let reason = match nm.reason {
						0 => EDIT_CHANGED_REASON::BY_INS_CHAR,
						1 => EDIT_CHANGED_REASON::BY_INS_CHARS,
						2 => EDIT_CHANGED_REASON::BY_DEL_CHAR,
						3 => EDIT_CHANGED_REASON::BY_DEL_CHARS,
						4 => EDIT_CHANGED_REASON::BY_UNDO_REDO,
						5 => EDIT_CHANGED_REASON::CHANGE_BY_INS_CONSECUTIVE_CHAR,
						6 => EDIT_CHANGED_REASON::CHANGE_BY_DEL_CONSECUTIVE_CHAR,
						7 => EDIT_CHANGED_REASON::CHANGE_BY_CODE,
						_ => return 0,
					};
					EventReason::EditChanged(reason)
				},

				BEHAVIOR_EVENTS::VIDEO_BIND_RQ => {
					EventReason::VideoBind(nm.reason as LPVOID)
				}

				_ => {
					let reason: CLICK_REASON = match nm.reason as UINT {
						0 => CLICK_REASON::BY_MOUSE_CLICK,
						1 => CLICK_REASON::BY_KEY_CLICK,
						2 => CLICK_REASON::SYNTHESIZED,
						3 => CLICK_REASON::BY_MOUSE_ON_ICON,
						_ => CLICK_REASON::SYNTHESIZED,
					};
					EventReason::General(reason)
				}
			};

			if he.is_null() && code != BEHAVIOR_EVENTS::MEDIA_CHANGED {
				eprintln!("[sciter] warning! null element for {:?}:{:?}", evtg, code);
			}

			if phase == PHASE_MASK::SINKING {	// catch this only once
				match code {
					BEHAVIOR_EVENTS::DOCUMENT_COMPLETE => {
						me.document_complete(he, nm.heTarget);
					},
					BEHAVIOR_EVENTS::DOCUMENT_CLOSE => {
						me.document_close(he, nm.heTarget);
					},
					_ => ()
				};
			}

			let handled = me.on_event(he, nm.he, nm.heTarget, code, phase, reason);
			handled
		},

		EVENT_GROUPS::HANDLE_SCRIPTING_METHOD_CALL => {
			assert!(!params.is_null());
			let scnm = params as *mut SCRIPTING_METHOD_PARAMS;
			let nm = unsafe { &mut *scnm };
			let name = u2s!(nm.name);
			let argv = unsafe { Value::unpack_from(nm.argv, nm.argc) };
			let rv = me.on_script_call(he, &name, &argv);
			let handled = if let Some(v) = rv {
				v.pack_to(&mut nm.result);
				true
			} else {
				false
			};
			handled
		},

    EVENT_GROUPS::HANDLE_METHOD_CALL => {
      assert!(!params.is_null());
      let scnm = params as *const METHOD_PARAMS;
      let nm = unsafe { & *scnm };
      let code: BEHAVIOR_METHOD_IDENTIFIERS = unsafe { ::std::mem::transmute((*nm).method) };
      use capi::scbehavior::BEHAVIOR_METHOD_IDENTIFIERS::*;

      // output values
      let mut method_value = Value::new();
      let mut is_empty = false;

      let handled = {

        // unpack method parameters
        use dom::event::MethodParams;
        let reason = match code {
          DO_CLICK => {
            MethodParams::Click
          },
          IS_EMPTY => {
            MethodParams::IsEmpty(&mut is_empty)
          },
          GET_VALUE => {
            MethodParams::GetValue(&mut method_value)
          },
          SET_VALUE => {
            // Value from Sciter.
            let payload = params as *const VALUE_PARAMS;
            let pm = unsafe { & *payload };
            MethodParams::SetValue(Value::from(&pm.value))
          },

          _ => {
            MethodParams::Custom((*nm).method, params)
          },
        };

        // call event handler
        let handled = me.on_method_call(he, reason);
        handled
      };

      if handled {
        // Pack values back to Sciter.
        match code {
          GET_VALUE => {
            let payload = params as *mut VALUE_PARAMS;
            let pm = unsafe { &mut *payload };
            method_value.pack_to(&mut pm.value);
          },

          IS_EMPTY => {
            let payload = params as *mut IS_EMPTY_PARAMS;
            let pm = unsafe { &mut *payload };
            pm.is_empty = is_empty as UINT;
          },

          _ => {},
        }
      }
      // we've done here
      handled
    },

		EVENT_GROUPS::HANDLE_TIMER => {
			assert!(!params.is_null());
			let scnm = params as *const TIMER_PARAMS;
			let nm = unsafe { & *scnm };
			let handled = me.on_timer(he, nm.timerId as u64);
			handled
		},

		EVENT_GROUPS::HANDLE_DRAW => {
			assert!(!params.is_null());
			let scnm = params as *const DRAW_PARAMS;
			let nm = unsafe { & *scnm };
			let handled = me.on_draw(he, nm.gfx, &nm.area, nm.layer);
			handled
		},

		// unknown `EVENT_GROUPS` notification
		_ => {
			eprintln!("[sciter] warning! unknown event group {:04X}", evtg as u32);
			false
		},
	};
	return result as BOOL;
}

#[cfg(test)]
mod checked_behavior_tests {
    use super::*;
    use capi::scvalue::{VALUE, VALUE_TYPE};
    use dom::event::EventReason;

    #[derive(Default)]
    struct Recorder { calls: usize }
    impl EventHandler for Recorder {
        fn on_event(&mut self, _: HELEMENT, _: HELEMENT, _: HELEMENT,
                    _: BEHAVIOR_EVENTS, _: PHASE_MASK, _: EventReason) -> bool {
            self.calls += 1;
            true
        }
    }

    fn dispatch(cmd: UINT, reason: UINT_PTR, handler: &mut Recorder) -> BOOL {
        let mut params = BEHAVIOR_EVENT_PARAMS {
            cmd, reason, heTarget: ::std::ptr::null_mut(), he: ::std::ptr::null_mut(),
            data: VALUE { t: VALUE_TYPE::T_UNDEFINED, u: 0, d: 0 },
            name: ::std::ptr::null(),
        };
        process_events(handler, ::std::ptr::null_mut(),
                       EVENT_GROUPS::HANDLE_BEHAVIOR_EVENT as UINT, &mut params as *mut _ as LPVOID)
    }

    #[test]
    fn menu_hover_0x1d_is_unhandled_in_every_phase() {
        let mut recorder = Recorder::default();
        for phase in [0, 0x8000, 0x10000, 0x18000].iter() {
            assert_eq!(dispatch(0x1d | phase, 0, &mut recorder), 0);
        }
        assert_eq!(recorder.calls, 0);
    }

    #[test]
    fn known_menu_events_still_reach_handler() {
        let mut recorder = Recorder::default();
        for code in [BEHAVIOR_EVENTS::MENU_ITEM_ACTIVE, BEHAVIOR_EVENTS::MENU_ITEM_CLICK,
                     BEHAVIOR_EVENTS::POPUP_READY, BEHAVIOR_EVENTS::POPUP_DISMISSED].iter() {
            assert_eq!(dispatch(*code as UINT, 0, &mut recorder), 1);
        }
        assert_eq!(recorder.calls, 4);
    }

    #[test]
    fn unknown_phase_and_edit_reason_are_unhandled() {
        let mut recorder = Recorder::default();
        assert_eq!(dispatch(BEHAVIOR_EVENTS::MENU_ITEM_ACTIVE as UINT | 0x20000, 0, &mut recorder), 0);
        assert_eq!(dispatch(BEHAVIOR_EVENTS::EDIT_VALUE_CHANGED as UINT, 255, &mut recorder), 0);
        assert_eq!(dispatch(BEHAVIOR_EVENTS::EDIT_VALUE_CHANGED as UINT, 7, &mut recorder), 1);
        assert_eq!(recorder.calls, 1);
    }
}
