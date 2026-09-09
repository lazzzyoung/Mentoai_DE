package config

import "testing"

func TestAdminUserIDs(t *testing.T) {
	for _, value := range []string{"1,x", "0", "-1", "1,", "9223372036854775808"} {
		if _, err := (Settings{AuthAdminUserIDs: value}).AdminUserIDs(); err == nil {
			t.Fatalf("accepted invalid setting %q", value)
		}
	}
	ids, err := (Settings{AuthAdminUserIDs: " 42, 7 "}).AdminUserIDs()
	if err != nil || len(ids) != 2 || ids[0] != 42 || ids[1] != 7 {
		t.Fatalf("%v %v", ids, err)
	}
	ids, err = (Settings{}).AdminUserIDs()
	if err != nil || len(ids) != 0 {
		t.Fatalf("empty allowlist: %v %v", ids, err)
	}
}
