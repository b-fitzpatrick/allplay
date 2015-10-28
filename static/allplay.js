var audioCtl = {
    
    lastUpdate: 0,
    pollErrors: 0,
    active: true,
    polling: false,
    hidden: "",
    error: true,
    
    update: function(r) {
        var masterVol = r[0];
        var cur_time = $.now();
        var spkrsDiv = $("#spkrs-div");
        var insert_index = 0;
        var spkrs = r[1];
        var master_active = false;
        // Update or insert speakers
        for (i = 0; i < spkrs.length; i++) {
            var spkr = spkrs[i];
            var id = spkr.msma;
            var name = spkr.minm;
            var active = spkr.caia == 1;
            if (active) master_active = true;
            var checked = active ? ' checked' : '';
            var vol = active ? (+masterVol * +spkr.cmvo / 100) : 0;
            // Look for existing speaker
            var spkrDiv = spkrsDiv.find("#" + id);
            if (spkrDiv.length == 1) {
                // Found existing speaker
                spkrDiv.find(".act-check").prop("checked", active)
                    .checkboxradio("refresh");
                spkrDiv.find(".vol-slider").val(vol).slider("refresh");
            } else {
                // New speaker
                spkrDiv = $('<div class="spkr" id=' + id + '/>');
                spkrDiv.append('<label for="act' + id + '">' + name + 
                               '</label>');
                spkrDiv.append('<input type="checkbox" ' +
                               'name="act' + id + '" id="act' + id + '"' +
                               'class="act-check"' + checked + '>');
                spkrDiv.append('<label for="vol' + id + '"' +
                               'class="ui-hidden-accessible">N/A</label>');
                spkrDiv.append('<input type="range" ' +
                               'name="vol' + id + '"' +
                               'id="vol' + id + '"' +
                               'class="vol-slider" ' +
                               'min="0" max="100" ' +
                               'value="' + vol + '" data-highlight="true">');
                if (spkrsDiv.children().length > insert_index) {
                    $(spkrsDiv.children()[insert_index]).before(spkrDiv);
                } else {
                    spkrsDiv.append(spkrDiv);
                }
                spkrDiv.trigger("create");
            }
            spkrDiv.data('ut', cur_time);
            insert_index++;
        }
        // Delete out-of-date speakers
        spkrsDiv.children().each(function(index) {
            if ($(this).data('ut') != cur_time) this.remove();
        });
        
        $("#act-master").prop("checked", master_active)
            .checkboxradio("refresh");
        $("#vol-master").val(masterVol).slider("refresh");
        
        // Pandora - Now Playing
        var now_playing = r[3];
        $("#pand_artist").html(now_playing.artist);
        $("#pand_title").html(now_playing.title);
        $("#pand_album").html(now_playing.album);
        $("#pand_cover").attr("src", now_playing.coverurl);
        if (now_playing.love == "1") {
            $("#pand_up").removeClass('ui-icon-pand_up').addClass('ui-icon-pand_up_set');
            console.log("Thumbs up");
        } else {
            $("#pand_up").removeClass('ui-icon-pand_up_set').addClass('ui-icon-pand_up');
            console.log("No thumbs up");
        }
        
        // Source List
        var staList = r[4];
        var selStation = $("#sel-station")
        selStation.empty();
        $.each(staList, function(id, name) {
            selStation
                .append($('<option>', {value : id})
                .text(name)
                .attr('selected', (name == now_playing.station)));
        });
        /*
        $.each(staList, function(id, name) {
            if (name == now_playing.station) {
                selStation
                    .append($('<option>', {value : id})
                    .text(name)
                    .attr('selected', 'selected'));
            } else {
                selStation
                    .append($('<option>', {value : id})
                    .text(name));
            }
        });
        */
        $("#sel-station").selectmenu().selectmenu('refresh', true);
    },
    
    poll: function() {
        if (!audioCtl.active) {
            audioCtl.polling = false;
            $("#restart").removeClass("ui-hidden-accessible");
            return;
        }
        audioCtl.polling = true;
        $.ajax({
            url: "poll",
            type: "GET",
            data: {last_update: audioCtl.lastUpdate},
            dataType: "json",
            success: function(response) {
                console.log("Poll response: " + JSON.stringify(response));
                audioCtl.pollErrors = 0;
                $("#restart").addClass("ui-hidden-accessible");
                if (response) {
                    audioCtl.update(response);
                    audioCtl.lastUpdate = response[2];
                }
                audioCtl.poll();
            },
            error: function(response) {
                console.log("Poll error: " + response);
                audioCtl.pollErrors++;
                if (audioCtl.pollErrors < 5) {
                    setTimeout(audioCtl.poll, 5000);
                } else {
                    $("#restart").removeClass("ui-hidden-accessible");
                    audioCtl.polling = false;
                }
            },
            global: false
        });
    },
    
    restart: function() {
        audioCtl.poll();
        $.ajax({
            url: "touch",
            type: "GET",
            dataType: "text"
        });
    },
    
    handleVisibility: function() {
        if (document[audioCtl.hidden]) {
            console.log("Lost visibility. Polling: " + audioCtl.polling);
            audioCtl.active = false;
        } else {
            console.log("Got visibility. Polling: " + audioCtl.polling);
            audioCtl.active = true;
            if (!audioCtl.polling) {
                audioCtl.poll();
            }
            $.ajax({
                url: "touch",
                type: "GET",
                dataType: "text"
            });
        }
    },
    
    init: function() {
        
        $(document).ajaxStart(function() {
            $.mobile.loading("show");
        });
        
        $(document).ajaxStop(function() {
            $.mobile.loading("hide");
        });
        
        var hidden, visibilityChange;
        if (typeof document.hidden !== "undefined") {
          hidden = "hidden";
          visibilityChange = "visibilitychange";
        } else if (typeof document.mozHidden !== "undefined") {
          hidden = "mozHidden";
          visibilityChange = "mozvisibilitychange";
        } else if (typeof document.msHidden !== "undefined") {
          hidden = "msHidden";
          visibilityChange = "msvisibilitychange";
        } else if (typeof document.webkitHidden !== "undefined") {
          hidden = "webkitHidden";
          visibilityChange = "webkitvisibilitychange";
        }
        audioCtl.hidden = hidden;
        document.addEventListener(visibilityChange, 
                                  $.debounce(100, audioCtl.handleVisibility),
                                  false);

        $("#act-master").on("change", function (event) {
            var activate = event.target.checked;
            if (activate) {
                if (!confirm("Activate all speakers?")) {
                    $(event.target).prop("checked", false)
                        .checkboxradio("refresh");
                    return false;
                }
                url = "act_spkr";
            } else {
                url = "deact_spkr";
            }
            $.ajax({
                url: url,
                type: "PUT",
                data: {id: "all"},
                dataType: "text",
                success: function(response) {
                    audioCtl.error = false;
                },
                error: function(response) {
                    audioCtl.error = true;
                    console.log("Response error: " + response);
                }
            });
            return false;
        });
        
        $("#vol-master").on("slidestop", function (event, ui) {
            var url;
            var data;
            var vol = event.target.value;
            if ($("#act-master").prop("checked")) {
                url = "set_mstr_vol";
                data = {vol: vol};
            } else if (vol > 0) {
                if (!confirm("Activate all speakers?")) {
                    $(event.target).val(0).slider("refresh");
                    return false;
                }
                url = "act_spkr";
                data = {id: "all", vol: vol};
            }
            $.ajax({
                url: url,
                type: "PUT",
                data: data,
                dataType: "text",
                success: function(response) {
                    audioCtl.error = false;
                },
                error: function(response) {
                    audioCtl.error = true;
                    console.log("Response error: " + response);
                }
            });
            return false;
        });
        
        $("#spkrs-div").on("change", ".act-check", function (event) {
            var url = event.target.checked ? "act_spkr" : "deact_spkr";
            var id = event.target.id.slice(3);
            $.ajax({
                url: url,
                type: "PUT",
                data: {id: id},
                dataType: "text",
                success: function(response) {
                    audioCtl.error = false;
                },
                error: function(response) {
                    audioCtl.error = true;
                    console.log("Response error: " + response);
                }
            });
            return false;
        });
        
        $("#spkrs-div").on("slidestop", ".vol-slider", function (event) {
            var id = event.target.id.slice(3);
            var vol = event.target.value;
            if ($("#act" + id).prop("checked")) {
                url = "spkr_vol";
            } else if (vol > 0) {
                url = "act_spkr";
            } else {
                return false;
            }
            $.ajax({
                url: url,
                type: "PUT",
                data: {vol: vol, id: id},
                dataType: "text",
                success: function(response) {
                    audioCtl.error = false;
                },
                error: function(response) {
                    audioCtl.error = true;
                    console.log("Response error: " + response);
                }
            });
            return false;
        });
        
        $("#sel-station").on("change", function() {
            var id = this.value;
            $.ajax({
                url: "pand_station",
                type: "PUT",
                data: {id: id},
                dataType: "text",
                success: function(response) {
                    audioCtl.error = false;
                },
                error: function(response) {
                    audioCtl.error = true;
                    console.log("Response error: " + response);
                }
            });
            $("#btn-source").focus();
            return false;
        });
        
        $("#pand_buttons").on("tap", "button", function(event) {
            url = $(event.target).attr("value");
            $.ajax({
                url: url,
                type: "GET",
                dataType: "text",
                success: function(response) {
                    audioCtl.error = false;
                },
                error: function(response) {
                    audioCtl.error = true;
                    console.log("Response error: " + response);
                }
            });
            $("#btn-source").focus();
            return false;
        });

        $("#reboot").on("click", function() {
            if (confirm("Are you sure you want to reboot the server?")) {
                url = "reboot";
                $.ajax({
                    url: url,
                    type: "GET",
                    dataType: "text",
                    success: function(response) {
                        audioCtl.error = false;
                    },
                    error: function(response) {
                        audioCtl.error = true;
                        console.log("Response error: " + response);
                    }
                });
            }
        });
        
        audioCtl.poll();
        
    }
};

(function(b,c){var $=b.jQuery||b.Cowboy||(b.Cowboy={}),a;$.throttle=a=function(e,f,j,i){var h,d=0;if(typeof f!=="boolean"){i=j;j=f;f=c}function g(){var o=this,m=+new Date()-d,n=arguments;function l(){d=+new Date();j.apply(o,n)}function k(){h=c}if(i&&!h){l()}h&&clearTimeout(h);if(i===c&&m>e){l()}else{if(f!==true){h=setTimeout(i?k:l,i===c?e-m:e)}}}if($.guid){g.guid=j.guid=j.guid||$.guid++}return g};$.debounce=function(d,e,f){return f===c?a(d,e,false):a(d,f,e!==false)}})(this);

$(document).ready(audioCtl.init);