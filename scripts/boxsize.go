// boxsize prints the Pigeonhole box plaintext size of the mixnet a client daemon config
// describes: the mesh must use the same size for its boxes to cross the bridge.
//
// Run inside a katzenpost checkout, whose module provides the packages:
//
//	cd katzenpost && go run /path/to/katzenrns/scripts/boxsize.go docker/mixnet-alpine/client/client.toml
package main

import (
	"fmt"
	"os"

	"github.com/katzenpost/katzenpost/client/config"
	pigeonholeGeo "github.com/katzenpost/katzenpost/pigeonhole/geo"
	replicaCommon "github.com/katzenpost/katzenpost/replica/common"
)

func main() {
	if len(os.Args) != 2 {
		fmt.Fprintln(os.Stderr, "usage: boxsize client.toml")
		os.Exit(2)
	}
	cfg, err := config.LoadFile(os.Args[1])
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	g, err := pigeonholeGeo.NewGeometryFromSphinx(cfg.SphinxGeometry, replicaCommon.NikeScheme)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	fmt.Println(g.MaxPlaintextPayloadLength)
}
